/** Fixed request settings for the local coding provider; no tools or logging. */
export default function (pi: any) {
  pi.on("before_provider_request", (event: any) => ({
    ...event.payload,
    temperature: 0.1,
    presence_penalty: 0,
    reasoning_effort: "none",
  }));
}
