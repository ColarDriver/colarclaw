export type SessionsUsageTotals = {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
  totalTokens: number;
  inputCost: number;
  outputCost: number;
  cacheReadCost: number;
  cacheWriteCost: number;
  totalCost: number;
};

export type SessionMessageCounts = {
  total: number;
  user: number;
  assistant: number;
  tool: number;
  errors: number;
};

export type SessionToolUsage = {
  totalCalls: number;
  tools: Array<{
    name: string;
    calls: number;
  }>;
};

export type SessionModelUsage = {
  provider?: string;
  model?: string;
  count: number;
  totals: SessionsUsageTotals;
};

export type SessionLatencyStats = {
  count: number;
  avgMs: number;
  minMs: number;
  maxMs: number;
  p95Ms: number;
};

export type SessionDailyLatency = SessionLatencyStats & {
  date: string;
};

export type SessionDailyModelUsage = {
  date: string;
  provider?: string;
  model?: string;
  count: number;
  cost: number;
  tokens: number;
};

export type SessionCostSummary = SessionsUsageTotals & {
  messageCounts?: SessionMessageCounts;
  toolUsage?: SessionToolUsage;
  modelUsage?: Array<{
    provider?: string;
    model?: string;
    input?: number;
    output?: number;
    cacheRead?: number;
    cacheWrite?: number;
    totalTokens?: number;
    totalCost?: number;
    count?: number;
  }>;
  firstActivity?: number;
  lastActivity?: number;
  durationMs?: number;
  latency?: SessionLatencyStats;
  dailyBreakdown?: Array<
    SessionsUsageTotals & {
      date: string;
    }
  >;
  dailyMessageCounts?: Array<{
    date: string;
    total: number;
    user: number;
    assistant: number;
    tool: number;
    errors: number;
  }>;
  dailyLatency?: SessionDailyLatency[];
  dailyModelUsage?: SessionDailyModelUsage[];
};

export type SessionUsageEntry = {
  key: string;
  label?: string;
  sessionId?: string;
  updatedAt?: number;
  agentId?: string;
  channel?: string;
  chatType?: string;
  origin?: {
    label?: string;
    provider?: string;
    surface?: string;
    chatType?: string;
    from?: string;
    to?: string;
    accountId?: string;
    threadId?: string | number;
  };
  modelOverride?: string;
  providerOverride?: string;
  modelProvider?: string;
  model?: string;
  usage: SessionCostSummary | null;
  contextWeight?: unknown;
};

export type SessionsUsageAggregates = {
  messages: SessionMessageCounts;
  tools: SessionToolUsage;
  byModel: SessionModelUsage[];
  byProvider: SessionModelUsage[];
  byAgent: Array<{ agentId: string; count?: number; totals: SessionsUsageTotals }>;
  byChannel: Array<{ channel: string; count?: number; totals: SessionsUsageTotals }>;
  latency?: SessionLatencyStats;
  dailyLatency?: SessionDailyLatency[];
  modelDaily?: SessionDailyModelUsage[];
  daily: Array<{
    date: string;
    tokens: number;
    cost: number;
    messages: number;
    toolCalls: number;
    errors: number;
  }>;
};

export type SessionsUsageResult = {
  updatedAt: number;
  startDate: string;
  endDate: string;
  sessions: SessionUsageEntry[];
  totals: SessionsUsageTotals;
  aggregates: SessionsUsageAggregates;
};
