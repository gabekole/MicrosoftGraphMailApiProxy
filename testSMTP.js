const nodemailer = require('nodemailer');

// Configure the SMTP transport to connect to your local SMTPS server
const transporter = nodemailer.createTransport({
  host: 'localhost',      // Your SMTP server hostname or IP
  port: 465,              // Port your SMTPS server is listening on
  secure: true,           // true because we're using SMTPS (TLS from the start)
  auth: {
    user: 'alice',        // username from your in-code user map
    pass: 'secret'        // corresponding password
  },
  tls: {
    // Accept self-signed certificates for testing
    rejectUnauthorized: false
  }
});

// Email options
const mailOptions = {
  from: '"Alice via Proxy" <test@example.com>',  // Sender address (should match one of the authorized mailboxes)
  to: 'test@example.com',                      // Recipient address
  subject: 'Test Email from SMTPS Client',           // Subject line
  text: 'Hello, this is a test email sent via our SMTPS proxy!',  // Plain text body
  html: '<p>Hello, this is a test email sent via our SMTPS proxy!</p>'  // HTML body (optional)
};

// Send email
transporter.sendMail(mailOptions, (error, info) => {
  if (error) {
    return console.error('Error occurred:', error);
  }
  console.log('Email sent successfully:', info.response);
  transporter.close();
});
