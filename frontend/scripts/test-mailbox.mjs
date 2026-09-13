// Local-only SMTP sink for fictional E2E accounts. Never run in a deployed environment.
import net from "node:net";
import http from "node:http";
const messages = [];
const smtp = net.createServer((socket) => {
  socket.setEncoding("utf8");
  socket.setTimeout(10000, () => socket.destroy());
  socket.write("220 localhost ESMTP test mailbox\r\n");
  let buffer = "",
    data = false,
    lines = [],
    recipient = "";
  socket.on("data", (chunk) => {
    buffer += chunk;
    if (buffer.length > 1000000) {
      socket.destroy();
      return;
    }
    while (buffer.includes("\r\n")) {
      const end = buffer.indexOf("\r\n"),
        line = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (data) {
        if (line !== ".") {
          lines.push(line.replace(/^\.\./, "."));
          continue;
        }
        const raw = lines.join("\r\n");
        const parts = raw.split("\r\n\r\n");
        let text = parts.slice(1).join("\r\n\r\n");
        if (/content-transfer-encoding: base64/i.test(parts[0]))
          text = Buffer.from(text.replace(/\s/g, ""), "base64").toString(
            "utf8",
          );
        if (/content-transfer-encoding: quoted-printable/i.test(parts[0]))
          text = text
            .replace(/=\r\n/g, "")
            .replace(/=([0-9A-F]{2})/gi, (_, hex) =>
              String.fromCharCode(parseInt(hex, 16)),
            );
        messages.push({ recipient, text });
        if (messages.length > 200) messages.shift();
        data = false;
        lines = [];
        socket.write("250 accepted\r\n");
        continue;
      }
      if (/^EHLO|^HELO/i.test(line)) socket.write("250 localhost\r\n");
      else if (/^MAIL FROM:/i.test(line)) socket.write("250 ok\r\n");
      else if (/^RCPT TO:/i.test(line)) {
        recipient = line
          .replace(/^RCPT TO:\s*</i, "")
          .replace(/>.*$/, "")
          .toLowerCase();
        socket.write(
          recipient.endsWith("@example.test")
            ? "250 ok\r\n"
            : "550 fictional example.test recipients only\r\n",
        );
      } else if (/^DATA$/i.test(line)) {
        data = true;
        socket.write("354 end with dot\r\n");
      } else if (/^QUIT$/i.test(line)) {
        socket.end("221 bye\r\n");
      } else socket.write("250 ok\r\n");
    }
  });
  socket.on("error", () => {});
});
smtp.listen(2525, "127.0.0.1");
http
  .createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    res.setHeader("Cache-Control", "no-store");
    const recipient = new URL(req.url, "http://127.0.0.1").searchParams.get(
      "recipient",
    );
    res.end(
      JSON.stringify(
        recipient
          ? messages.filter((m) => m.recipient === recipient)
          : { status: "ok" },
      ),
    );
  })
  .listen(8025, "127.0.0.1");
console.log("Fictional SMTP mailbox ready on loopback ports 2525/8025.");
