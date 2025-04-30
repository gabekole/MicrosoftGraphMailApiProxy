const { SMTPServer } = require('smtp-server');
const { simpleParser } = require('mailparser');
const { Client } = require('@microsoft/microsoft-graph-client');
const { ConfidentialClientApplication } = require('@azure/msal-node');
require('isomorphic-fetch');
const fs = require('fs');
require('dotenv').config();  // Load .env file


const tenantId = process.env.TENANT_ID;
const clientId = process.env.CLIENT_ID;
const clientSecret = process.env.CLIENT_SECRET;

// In-code user map: username -> { password, mailboxes allowed }
const users = {
  'alice': { password: 'secret', mailboxes: ['test@example.com'] }
};

if (!tenantId || !clientId || !clientSecret) {
  throw new Error("Azure configuration environment variables missing.");
}

// Initialize MSAL client for token acquisition
const msalClient = new ConfidentialClientApplication({
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    clientSecret,
  },
});

// Acquire an access token for Microsoft Graph using client credentials flow
async function getAccessToken() {
  const tokenRequest = { scopes: ["https://graph.microsoft.com/.default"] };
  const response = await msalClient.acquireTokenByClientCredential(tokenRequest);
  if (!response?.accessToken) throw new Error("Failed to acquire access token");
  return response.accessToken;
}

// Send an email via Microsoft Graph API on behalf of a specific mailbox
async function sendEmailViaGraphAPI(mailbox, recipients, subject, body) {
  const accessToken = await getAccessToken();
  const graphClient = Client.init({ authProvider: (done) => done(null, accessToken) });

  const message = {
    subject,
    body: {
      contentType: "HTML",
      content: body,
    },
    toRecipients: recipients.map(email => ({ emailAddress: { address: email } })),
  };

  await graphClient.api(`/users/${mailbox}/sendMail`).post({ message, saveToSentItems: true });
}

// Create the SMTP server configuration with SMTPS support
const server = new SMTPServer({
  secure: true,  // Start directly with a TLS-encrypted connection
  tls: {
    key: fs.readFileSync('private-key.pem'),
    cert: fs.readFileSync('certificate.pem'),
    rejectUnauthorized: false, // Allow self-signed certificates
  },

  authOptional: false,

  // Authentication callback
  onAuth(auth, session, callback) {
    const { username, password } = auth;
    if (users[username] && users[username].password === password) {
      session.user = username;
      return callback(null, { user: username });
    }
    return callback(new Error("Invalid username or password"));
  },

  // Validate the MAIL FROM address against user's authorized mailboxes
  onMailFrom(address, session, callback) {
    const username = session.user;
    const user = users[username];
    if (user && user.mailboxes.includes(address.address)) {
      session.mailbox = address.address;
      return callback();
    }
    return callback(new Error("Not authorized to send from this mailbox"));
  },

  // Handle incoming email data
  onData(stream, session, callback) {
    simpleParser(stream, {}, async (err, parsed) => {
      if (err) {
        console.error('Error parsing email:', err);
        return callback(err);
      }
      try {
        const mailbox = session.mailbox;
        if (!mailbox) throw new Error("No authorized mailbox found");

        // Extract recipients from SMTP envelope
        const recipients = session.envelope.rcptTo.map(rcpt => rcpt.address);
        const subject = parsed.subject || "(No Subject)";
        const body = parsed.html || parsed.text || "";

        await sendEmailViaGraphAPI(mailbox, recipients, subject, body);
        callback();  // Signal successful handling of the message
      } catch (sendError) {
        console.error('Error sending email via Graph API:', sendError);
        callback(sendError);
      }
    });
  },
});

// Start the SMTP server
server.listen(465, () => {  // Use port 465 for SMTPS
  console.log('SMTP server listening on port 465 (secure)');
});

server.on("error", (err) => {
  console.error("SMTP Server encountered an error:", err);
});