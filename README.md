# Microsoft Graph Mail Proxy

An usecure email proxy that connects standard mail clients to Microsoft Graph API, enabling access to Microsoft 365 mailboxes via traditional POP3S and SMTPS protocols.

## Overview

Graph Mail Proxy acts as a bridge between standard email clients (Thunderbird, Outlook, mobile apps, etc.) and Microsoft 365 mailboxes accessed through Microsoft Graph API. It provides:

- A secure POP3 server (POP3S on port 995) to retrieve emails from Microsoft 365 mailboxes  
- A secure SMTP server (SMTPS on port 465) to send emails via Microsoft 365 mailboxes  
- Support for multiple users with access to shared mailboxes  
- TLS encryption throughout for secure communication  

## Architecture

The project is structured into three main components:

1. **POP3 Proxy Server** (`pop3_proxy.py`): A Twisted-based POP3 server that:
   - Authenticates users against a local user database
   - Fetches emails from Microsoft Graph API
   - Presents mailbox contents in standard POP3 format
   - Handles delete operations by making appropriate Graph API calls

2. **SMTP Proxy Server** (`smtpServer.js`): A Node.js SMTP server that:
   - Accepts incoming emails from clients through SMTPS
   - Authenticates sending users
   - Verifies they have permission to use the specified "From" address
   - Forwards emails to Microsoft Graph API for delivery

3. **Certificate Generation** (`make_keys.js`): A utility to generate self-signed TLS certificates for secure connections.

## Prerequisites

- Node.js 14+  
- Python 3.6+  
- An Azure AD application with:
  - Client credentials (client ID and secret)
  - Microsoft Graph API permissions for mail operations

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/graph-mail-proxy.git
   cd graph-mail-proxy
   ```

2. Install Node.js dependencies:
   ```bash
   npm install selfsigned poplib nodemailer smtp-server mailparser @microsoft/microsoft-graph-client @azure/msal-node isomorphic-fetch dotenv
   ```

3. Install Python dependencies:
   ```bash
   pip install twisted msal requests python-dotenv
   ```

4. Generate self-signed certificates:
   ```bash
   node make_keys.js
   ```

5. Create a `.env` file in the root of your project:
   ```
   TENANT_ID=your-tenant-id
   CLIENT_ID=your-client-id
   CLIENT_SECRET=your-client-secret
   ```

   > 🔐 Do **not** commit this file to version control.

## Configuration

### Azure AD Configuration

1. Configure an Azure AD application with the following:
   - **Client ID**, **Tenant ID**, and **Client Secret**
   - API permissions:
     - `Mail.ReadWrite`
     - `Mail.Send`
     - `User.Read.All`

2. Ensure the `.env` file contains:
   ```
   TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   CLIENT_SECRET=your-client-secret
   ```

### User Configuration

Users are defined in code. Edit the `USERS` variable in both `pop3_proxy.py` and `smtpServer.js`:

```javascript
const users = {
  'alice': { password: 'secret', mailboxes: ['shared@example.com'] },
  'bob': { password: 'hunter2', mailboxes: ['shared@example.com'] },
};
```

> ⚠️ These credentials are only suitable for testing. For production, use a secure user store.

## Usage

1. Start the POP3 proxy server:
   ```bash
   python pop3_proxy.py
   ```

2. Start the SMTP proxy server:
   ```bash
   node smtpServer.js
   ```

3. Configure your email client:
   - **Incoming Mail (POP3)**:
     - Server: `localhost` (or server IP)
     - Port: `995`
     - Security: SSL/TLS
     - Authentication: Normal password
     - Username: as defined (e.g., `alice`)
     - Password: as defined (e.g., `secret`)

   - **Outgoing Mail (SMTP)**:
     - Server: `localhost` (or server IP)
     - Port: `465`
     - Security: SSL/TLS
     - Authentication: Normal password
     - Username: as defined
     - Password: as defined

## Testing

Use the included test scripts:

```bash
node testPOP3.js
node testSMTP.js
```

## Security Considerations

- TLS encryption is enforced on both POP3 and SMTP servers  
- Secrets (client credentials) are now stored securely using environment variables  
- User authentication is basic and in-code — improve this for production  
- Self-signed certificates are provided for local use — replace with valid certificates for production  

## Limitations

- No IMAP support  
- Static, in-code user configuration  
- Minimal error handling and retry logic  
- No certificate management or web-based UI  

## Future Enhancements

- Move user data to a persistent database  
- Add support for IMAP  
- Implement robust logging and retry logic  
- Add a web UI for configuration  
- Support user-specific mailbox routing  
- Integrate certificate management (Let's Encrypt or similar)  

## Acknowledgements

- [Twisted](https://twisted.org/) for the POP3 server  
- [smtp-server](https://nodemailer.com/extras/smtp-server/) for SMTP handling  
- Microsoft Graph SDKs for API access  
