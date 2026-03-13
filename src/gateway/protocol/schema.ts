type JsonSchema = {
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  enum?: string[];
  patternProperties?: Record<string, JsonSchema>;
};

export const PROTOCOL_VERSION = 1;

export const ErrorCodes = [
  "invalid_request",
  "unauthorized",
  "forbidden",
  "not_found",
  "conflict",
  "internal_error",
] as const;

export const ProtocolSchemas: Record<string, JsonSchema> = {};
