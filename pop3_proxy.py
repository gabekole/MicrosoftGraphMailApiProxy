#!/usr/bin/env python3
"""
A secure POP3 proxy server using Twisted that fetches mail from Microsoft Graph.
"""

import os
import ssl
import email
import io
import time
import logging
from typing import List

from twisted.internet import reactor, protocol, ssl as twisted_ssl
from twisted.cred import portal, credentials

from twisted.cred.error import UnauthorizedLogin
from twisted.mail import pop3
from twisted.cred.portal import IRealm
from twisted.cred.checkers import ICredentialsChecker

from zope.interface import implementer

# MSAL for acquiring tokens via Client Credentials
from msal import ConfidentialClientApplication

# We'll use the requests-based approach with MSAL
import requests

import email
from email.parser import BytesParser
from dotenv import load_dotenv
load_dotenv()


##############################
# Logging Configuration
##############################
logger = logging.getLogger("POP3ProxyServer")
logger.setLevel(logging.DEBUG)

# Console handler for logging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(name)s - %(message)s")
console_handler.setFormatter(console_formatter)

# File handler for logging
file_handler = logging.FileHandler("pop3_proxy.log")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(name)s - %(message)s")
file_handler.setFormatter(file_formatter)

# Add handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

##############################
# 1) Graph / Azure Settings
##############################

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")


# Scopes for Microsoft Graph; using .default covers mailbox operations
SCOPES = ["https://graph.microsoft.com/.default"]

# Initialize the MSAL confidential client
logger.debug("Initializing MSAL ConfidentialClientApplication.")
msal_app = ConfidentialClientApplication(
    client_id=CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    client_credential=CLIENT_SECRET
)

# Simple user map: username -> { password, mailboxes: [list_of_email_addresses] }
USERS = {
    'alice': { 'password': 'secret',   'mailboxes': ['test@example.com'] }
}

##############################
# 2) Graph Helper Functions
##############################

def get_access_token() -> str:
    logger.debug("Attempting to acquire access token from Microsoft Graph.")
    result = msal_app.acquire_token_for_client(scopes=SCOPES)
    if 'access_token' not in result:
        logger.error("Failed to obtain access token: %s", result.get("error_description", result))
        raise Exception("Failed to obtain access token: %s" % result.get("error_description"))
    logger.info("Successfully obtained Microsoft Graph access token.")
    return result['access_token']

def graph_list_messages(mailbox: str, top: int = 10) -> List[dict]:
    logger.debug("Listing messages for mailbox '%s'; retrieving top %d.", mailbox, top)
    token = get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages?$top={top}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    messages = data.get('value', [])
    logger.info("Fetched %d messages for mailbox '%s'.", len(messages), mailbox)
    return messages

def graph_get_message_raw(mailbox: str, message_id: str) -> bytes:
    logger.debug("Fetching raw message content for mailbox '%s', message ID '%s'.", mailbox, message_id)
    token = get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{message_id}/$value"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/octet-stream"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    logger.info("Retrieved raw content for message ID '%s'.", message_id)
    return resp.content

def graph_delete_message(mailbox: str, message_id: str) -> None:
    logger.debug("Deleting message ID '%s' from mailbox '%s'.", message_id, mailbox)
    token = get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{message_id}"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    resp.raise_for_status()
    logger.info("Successfully deleted message ID '%s' from mailbox '%s'.", message_id, mailbox)


##############################
# 3) Custom Twisted POP3 Classes
##############################

class GraphMailbox(pop3.Mailbox):
    """
    A "mailbox" that fetches messages from Microsoft Graph.
    Implements the pop3.IMailbox interface.
    """
    def __init__(self, mailbox: str):
        super().__init__()
        self.mailbox = mailbox
        self._messages = []   # list of (msgId, raw_mime)
        self._deleted = set() # track message indices flagged for deletion
        logger.debug("Initialized GraphMailbox for '%s'.", mailbox)
    

    def retrieve(self, index: int):
        """
        Retrieve the raw content of a message by its index.

        @type index: int
        @param index: The 0-based index of the message.
        @rtype: file-like object (BytesIO)
        @return: A file containing the raw MIME content of the message.
        @raise ValueError or IndexError: When the index does not correspond to
            a message in the mailbox. The use of ValueError is preferred.
        """
        logger.debug("Retrieving message at index %d for mailbox '%s'.", index, self.mailbox)
        if index < 0 or index >= len(self._messages):
            logger.error("Message index %d out of range for mailbox '%s'.", index, self.mailbox)
            raise IndexError("Message index out of range")
        if index in self._deleted:
            logger.warning("Attempt to retrieve a deleted message at index %d in mailbox '%s'.", index, self.mailbox)
            raise ValueError("Message deleted")

        msg_id, raw_mime = self._messages[index]
        if raw_mime is None:
            try:
                logger.debug("Fetching raw MIME content for message ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
                raw_mime = graph_get_message_raw(self.mailbox, msg_id)
                self._messages[index] = (msg_id, raw_mime)  # Cache the raw MIME content
            except Exception as e:
                logger.exception("Failed to retrieve message content for ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
                raise ValueError(f"Could not retrieve message content: {e}")

        logger.info("Successfully retrieved message ID '%s' from mailbox '%s'.", msg_id, self.mailbox)
        return io.BytesIO(raw_mime)

    def getUidl(self, index):
        logger.debug("getUidl called for mailbox '%s', index %d.", self.mailbox, index)
        if index < 0 or index >= len(self._messages):
            logger.error("Message index %d out of range for mailbox '%s'.", index, self.mailbox)
            raise IndexError("Message index out of range")
        msg_id, _ = self._messages[index]
        # Use the message ID as the unique identifier
        logger.info("Returning UIDL for message index %d in mailbox '%s'.", index, self.mailbox)
        return msg_id.encode('utf-8')

    def sync_messages(self):
        logger.info("Synchronizing messages for mailbox '%s'.", self.mailbox)
        try:
            messages = graph_list_messages(self.mailbox, top=50)
        except Exception:
            logger.exception("Error fetching messages for mailbox '%s'.", self.mailbox)
            messages = []
        
        self._messages = [(msg['id'], None) for msg in messages]
        self._deleted = set()
        logger.debug("Mailbox '%s' now has %d messages loaded.", self.mailbox, len(self._messages))
    
    def listMessages(self, index=None):
        logger.debug("Listing messages for mailbox '%s'. Index requested: %s", self.mailbox, str(index))
        if not self._messages:
            self.sync_messages()
        
        if index is not None:
            return self._get_message_size(index)
        else:
            return [self._get_message_size(i) for i in range(len(self._messages))]
    
    def _get_message_size(self, index: int) -> int:
        if index < 0 or index >= len(self._messages):
            logger.error("Message index %d out of range for mailbox '%s'.", index, self.mailbox)
            raise IndexError("Message index out of range")
        
        if index in self._deleted:
            logger.debug("Message at index %d is marked deleted in mailbox '%s'.", index, self.mailbox)
            return 0
        
        msg_id, raw_mime = self._messages[index]
        if raw_mime is None:
            try:
                logger.debug("Fetching raw content for message '%s' in mailbox '%s'.", msg_id, self.mailbox)
                raw_mime = graph_get_message_raw(self.mailbox, msg_id)
                self._messages[index] = (msg_id, raw_mime)
            except Exception:
                logger.exception("Failed to retrieve message content for ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
                return 0
        
        size = len(raw_mime)
        logger.debug("Size of message '%s' in mailbox '%s' is %d bytes.", msg_id, self.mailbox, size)
        return size
    
    def getMessage(self, index):
        logger.debug("getMessage called for mailbox '%s', index %d.", self.mailbox, index)
        if index < 0 or index >= len(self._messages):
            logger.error("Message index %d out of range for mailbox '%s'.", index, self.mailbox)
            raise IndexError("Message index out of range")
        if index in self._deleted:
            logger.warning("Attempt to get a deleted message at index %d in mailbox '%s'.", index, self.mailbox)
            raise IndexError("Message deleted")
        
        msg_id, raw_mime = self._messages[index]
        if raw_mime is None:
            try:
                logger.debug("Fetching raw content (getMessage) for ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
                raw_mime = graph_get_message_raw(self.mailbox, msg_id)
                self._messages[index] = (msg_id, raw_mime)
            except Exception:
                logger.exception("Failed to retrieve message content for ID '%s' in mailbox '%s'. Returning empty content.", msg_id, self.mailbox)
                return io.BytesIO(b"")
        
        logger.info("Delivering message ID '%s' from mailbox '%s'.", msg_id, self.mailbox)
        # Parse the raw MIME content into an EmailMessage object
        logger.info("Parsing message ID '%s' into EmailMessage object.", msg_id)
        message = BytesParser().parsebytes(raw_mime)

        # Serialize the message back into raw bytes and wrap in BytesIO
        serialized_message = message.as_bytes()
        return io.BytesIO(serialized_message)


    def getMessageCount(self):
        logger.debug("Retrieving message count for mailbox '%s'.", self.mailbox)
        if not self._messages:
            self.sync_messages()
        count = len(self._messages) - len(self._deleted)
        logger.info("Mailbox '%s' has %d available messages.", self.mailbox, count)
        return count
    
    def deleteMessage(self, index):
        logger.debug("deleteMessage called for mailbox '%s', index %d.", self.mailbox, index)
        if index < 0 or index >= len(self._messages):
            logger.error("Message index %d out of range for mailbox '%s'.", index, self.mailbox)
            raise IndexError("Message index out of range")
        self._deleted.add(index)
        logger.info("Message at index %d marked for deletion in mailbox '%s'.", index, self.mailbox)
    
    def undeleteMessages(self):
        logger.info("Undeleting all messages in mailbox '%s'.", self.mailbox)
        self._deleted.clear()
    
    def sync(self):
        """
        Permanently delete all messages that were flagged for deletion 
        (i.e., finalize the deletions).
        """
        logger.debug("Finalizing deletions for mailbox '%s'.", self.mailbox)
        for index in self._deleted:
            if 0 <= index < len(self._messages):
                msg_id, _ = self._messages[index]
                try:
                    logger.debug("Deleting message ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
                    graph_delete_message(self.mailbox, msg_id)
                    logger.info("Deleted message ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
                except Exception:
                    logger.exception("Failed to delete message ID '%s' in mailbox '%s'.", msg_id, self.mailbox)
        self._deleted.clear()
        logger.debug("Deletion sync complete for mailbox '%s'.", self.mailbox)

@implementer(IRealm)
class GraphPOP3Realm():
    """
    A Twisted Realm that returns a custom GraphMailbox for each logged-in user.
    """
    def requestAvatar(self, avatarId, mind, *interfaces):
        logger.debug("Requesting avatar for user '%s'.", avatarId)
        if pop3.IMailbox in interfaces:
            userRecord = USERS.get(avatarId, {})
            mailboxes = userRecord.get('mailboxes', [])
            if not mailboxes:
                logger.error("No mailbox configured for user '%s'.", avatarId)
                raise Exception("No mailbox configured for user")

            mailbox = mailboxes[0]
            mbox = GraphMailbox(mailbox)
            logger.info("Provided mailbox '%s' for user '%s'.", mailbox, avatarId)
            return pop3.IMailbox, mbox, lambda: mbox.sync()
        logger.error("No appropriate interface found for user '%s'.", avatarId)
        raise NotImplementedError("No interface for " + str(interfaces))

##############################
# 4) Twisted Setup, SSL, and Custom POP3 Factory
##############################

@implementer(ICredentialsChecker)
class SimpleInMemoryChecker():
    """
    A basic credentials checker that validates against an in-memory user map.
    """
    credentialInterfaces = (credentials.IUsernamePassword,)

    def requestAvatarId(self, credentials):
        username = credentials.username.decode("utf-8")
        password = credentials.password.decode("utf-8")
        logger.debug("Authenticating user '%s' with SimpleInMemoryChecker.", username)

        if username in USERS and USERS[username]['password'] == password:
            logger.info("User '%s' authenticated successfully.", username)
            return username
        logger.warning("Invalid login attempt for user '%s'.", username)
        raise UnauthorizedLogin("Invalid username or password")


class CustomPOP3Protocol(pop3.POP3):
    """
    Custom implementation of the POP3 protocol.
    """
    def connectionMade(self):
        logger.info("Connection established from %s", self.transport.getPeer())
        super().connectionMade()
        self.timeout = 600  # 10-minute inactivity timeout

    def connectionLost(self, reason):
        logger.info("Connection lost from %s: %s", self.transport.getPeer(), reason)
        super().connectionLost(reason)


class CustomPOP3Factory(protocol.Factory):
    """
    Factory to produce instances of the custom POP3 protocol.
    """
    def __init__(self, portal):
        self.portal = portal

    def buildProtocol(self, addr):
        logger.debug("Building POP3 protocol for incoming connection from %s.", addr)
        proto = CustomPOP3Protocol()
        proto.portal = self.portal
        return proto


def main():
    logger.info("Starting Secure POP3 Proxy Server setup...")

    pop3_portal = portal.Portal(GraphPOP3Realm())
    pop3_portal.registerChecker(SimpleInMemoryChecker())

    factory = CustomPOP3Factory(pop3_portal)

    # SSL context setup
    logger.info("Setting up SSL context.")
    sslContext = twisted_ssl.DefaultOpenSSLContextFactory(
        'private-key.pem',
        'certificate.pem',
    )
    # Restrict to secure TLS versions only
    sslContext.getContext().set_options(
        ssl.OP_NO_TLSv1 | 
        ssl.OP_NO_TLSv1_1 |
        ssl.OP_NO_SSLv2 |
        ssl.OP_NO_SSLv3 |
        ssl.OP_NO_RENEGOTIATION |
        ssl.OP_CIPHER_SERVER_PREFERENCE
    )

    try:
        reactor.listenSSL(995, factory, sslContext)
        logger.info("Secure POP3 proxy server is running on port 995 (SSL).")
    except Exception:
        logger.exception("Failed to listen on port 995. Exiting.")
        return

    logger.info("Entering Twisted reactor event loop.")
    reactor.run()

if __name__ == "__main__":
    main()
