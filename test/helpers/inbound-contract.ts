import { expect } from "vitest";
import { resolveConversationLabel } from "../../src/channels/conversation-label.js";
import { validateSenderIdentity } from "../../src/channels/sender-identity.js";
import type { MsgContext } from "../../ui/src/ui/compat/auto-reply/templating.js";
import { normalizeChatType } from "../../ui/src/ui/compat/channels/chat-type.js";

export function expectInboundContextContract(ctx: MsgContext) {
  expect(validateSenderIdentity(ctx)).toEqual([]);

  expect(ctx.Body).toBeTypeOf("string");
  expect(ctx.BodyForAgent).toBeTypeOf("string");
  expect(ctx.BodyForCommands).toBeTypeOf("string");

  const chatType = normalizeChatType(ctx.ChatType);
  if (chatType && chatType !== "direct") {
    const label = ctx.ConversationLabel?.trim() || resolveConversationLabel(ctx);
    expect(label).toBeTruthy();
  }
}
