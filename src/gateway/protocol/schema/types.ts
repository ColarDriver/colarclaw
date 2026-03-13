export type ToolCatalogProfile = {
  id: string;
  label: string;
  description?: string;
  allow?: string[];
  deny?: string[];
};

export type ToolCatalogEntry = {
  id: string;
  label: string;
  description: string;
  source?: "core" | "plugin";
  pluginId?: string;
  optional?: boolean;
  defaultProfiles: string[];
};

export type ToolCatalogGroup = {
  id: string;
  label: string;
  source?: "core" | "plugin";
  pluginId?: string;
  tools: ToolCatalogEntry[];
};

export type ToolsCatalogResult = {
  agentId: string;
  profiles: ToolCatalogProfile[];
  groups: ToolCatalogGroup[];
};
