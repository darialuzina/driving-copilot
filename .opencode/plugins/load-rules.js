// Project-local OpenCode plugin: asks the agent to load the project rules on session start.
export const LoadRules = async ({ client }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.start") {
        await client.session.prompt({
          parts: [{
            type: "text",
            text: "Read the root AGENTS.md before starting work. It will tell you which .agents/* rules and skills apply to the current task.",
          }],
        });
      }
    },
  };
};
