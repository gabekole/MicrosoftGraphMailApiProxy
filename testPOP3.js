const POP3Client = require("poplib");

const config = {
  host: "127.0.0.1", // Replace with your POP3 server's address
  port: 995,         // Port for POP3S (secure POP3)
  tls: true,         // Enable TLS for secure connections
  user: "alice",     // Replace with the username for authentication
  password: "secret" // Replace with the password for authentication
};

// Create a POP3 client
const client = new POP3Client(config.port, config.host, {
  enabletls: config.tls,
  ignoretlserrs: true, // Set to true if testing with self-signed certificates
});

client.on("connect", () => {
  console.log("Connected to the POP3 server.");

  // Authenticate the user
  client.login(config.user, config.password);
});

client.on("login", (status, rawData) => {
  if (status) {
    console.log("Authentication successful.");
    // Request the list of messages
    client.list();
  } else {
    console.error("Authentication failed:", rawData);
    client.quit();
  }
});

client.on("list", (status, msgCount, msgData, rawData) => {
  if (status) {
    console.log(`Mailbox contains ${msgCount} messages.`);

    if (msgCount > 0) {
      // Retrieve the first message
      client.retr(1);
    } else {
      console.log("No messages to retrieve.");
      client.quit();
    }
  } else {
    console.error("Failed to list messages:", rawData);
    client.quit();
  }
});

client.on("retr", (status, msgNumber, msgData, rawData) => {
  if (status) {
    console.log(`Retrieved message #${msgNumber}:`);
    console.log(msgData);
  } else {
    console.error(`Failed to retrieve message #${msgNumber}:`, rawData);
  }
  client.quit();
});

client.on("quit", (status, rawData) => {
  console.log("Disconnected from the server.");
});

client.on("error", (err) => {
  console.error("An error occurred:", err);
  client.quit();
});
