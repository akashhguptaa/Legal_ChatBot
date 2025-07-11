export async function streamSummary(
  file: File,
  sessionId: string | null,
  onChunk: (chunk: string) => void,
  onStatus?: (status: string, message: string) => void
): Promise<string | null> {
  const formData = new FormData();
  formData.append("file", file);

  // Add session_id if available (can be null)
  console.log("Streaming utility received sessionId:", sessionId); // Debug log
  if (sessionId) {
    formData.append("session_id", sessionId);
    console.log("Added session_id to formData:", sessionId); // Debug log
  } else {
    console.log("No session_id to add to formData"); // Debug log
  }

  const response = await fetch("http://localhost:8000/upload/summary", {
    method: "POST",
    body: formData,
  });

  if (!response.body) throw new Error("No response body");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let done = false;
  let confirmedSessionId: string | null = null;

  while (!done) {
    const { value, done: doneReading } = await reader.read();
    if (value) {
      const chunk = decoder.decode(value);
      console.log("Raw chunk received:", chunk); // Debug log

      const lines = chunk.split("\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const jsonStr = line.slice(6);
            console.log("Parsing JSON:", jsonStr); // Debug log
            const data = JSON.parse(jsonStr);

            if (data.status === "session_id" && data.session_id) {
              console.log("Received session_id confirmation:", data.session_id); // Debug log
              confirmedSessionId = data.session_id;
            } else if (data.status === "summary_chunk" && data.content) {
              console.log("Sending content chunk:", data.content); // Debug log
              onChunk(data.content);
            } else if (
              onStatus &&
              data.status !== "summary_chunk" &&
              data.status !== "session_id"
            ) {
              console.log("Sending status:", data.status, data.message); // Debug log
              onStatus(data.status, data.message);
            }
          } catch (e) {
            console.log("JSON parse error:", e); // Debug log
            // Fallback: treat as regular content
            onChunk(line.slice(6));
          }
        }
      }
    }
    done = doneReading;
  }

  return confirmedSessionId;
}
