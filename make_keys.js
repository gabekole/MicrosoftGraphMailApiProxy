const selfsigned = require('selfsigned');
const fs = require('fs');
const path = require('path');

// Define certificate attributes and options
const attrs = [{ name: 'commonName', value: 'localhost' }];
const options = {
  days: 365,                // Validity period
  algorithm: 'sha256',      // Signing algorithm
  keySize: 2048,            // RSA key size
};

// Generate the self-signed certificate and private key
const pems = selfsigned.generate(attrs, options);

// Define file paths relative to the current script directory
const keyPath = path.join(__dirname, 'private-key.pem');
const certPath = path.join(__dirname, 'certificate.pem');

// Write the key and certificate to files
fs.writeFileSync(keyPath, pems.private, { encoding: 'utf8' });
fs.writeFileSync(certPath, pems.cert, { encoding: 'utf8' });

console.log(`Generated certificate at: ${certPath}`);
console.log(`Generated private key at: ${keyPath}`);
