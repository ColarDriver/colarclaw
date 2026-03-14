export type MsgContext = {
  Body?: string;
  BodyForAgent?: string;
  BodyForCommands?: string;
  ChatType?: string;
  ConversationLabel?: string;
  [key: string]: unknown;
};
