import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { mcpServersApi, specsApi } from '../api/client';
import type { LogicalGroup, McpServerRecord, McpServerStatus, McpTreeResponse } from '../types';

export const queryKeys = {
  specs: ['specifications'] as const,
  spec: (id: string) => ['specification', id] as const,
  mcpServers: ['mcp-servers'] as const,
  mcpTree: ['mcp-tree'] as const,
};

export function useSpecifications() {
  return useQuery({
    queryKey: queryKeys.specs,
    queryFn: specsApi.list,
  });
}

export function useSpecification(id: string | null) {
  return useQuery({
    queryKey: queryKeys.spec(id ?? ''),
    queryFn: () => specsApi.get(id!),
    enabled: Boolean(id),
  });
}

export function useUploadSpec() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.upload,
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.specs }),
  });
}

export function useDeleteSpec() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.specs });
      qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
      qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
    },
  });
}

export function useParseSpec() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.parse,
    onSuccess: (_data, specId) => {
      qc.invalidateQueries({ queryKey: queryKeys.specs });
      qc.invalidateQueries({ queryKey: queryKeys.spec(specId) });
    },
  });
}

export function useGenerateMetadata() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: specsApi.generateMetadata,
    onSuccess: (_data, specId) => {
      qc.invalidateQueries({ queryKey: queryKeys.specs });
      qc.invalidateQueries({ queryKey: queryKeys.spec(specId) });
    },
  });
}

export function useMcpServers() {
  return useQuery({
    queryKey: queryKeys.mcpServers,
    queryFn: mcpServersApi.list,
  });
}

export function useMcpTree() {
  return useQuery({
    queryKey: queryKeys.mcpTree,
    queryFn: mcpServersApi.tree,
  });
}

export function useGroupEndpoints() {
  return useMutation({
    mutationFn: ({ specId, keys }: { specId: string; keys: string[] }) =>
      mcpServersApi.group(specId, keys),
  });
}

export function useWizardGenerate() {
  return useMutation({
    mutationFn: ({ specId, groups }: { specId: string; groups: LogicalGroup[] }) =>
      mcpServersApi.wizardGenerate(specId, groups),
  });
}

export function useWizardSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      batchId,
      servers,
    }: {
      batchId: string;
      servers: Parameters<typeof mcpServersApi.wizardSave>[1];
    }) => mcpServersApi.wizardSave(batchId, servers),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
      qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
    },
  });
}

function patchServerStatusInTree(
  tree: McpTreeResponse | undefined,
  serverId: string,
  status: McpServerStatus,
): McpTreeResponse | undefined {
  if (!tree) return tree;
  return {
    ...tree,
    specifications: tree.specifications.map((spec) => ({
      ...spec,
      servers: spec.servers.map((server) =>
        server.id === serverId ? { ...server, status } : server,
      ),
    })),
  };
}

function syncServerStatus(qc: ReturnType<typeof useQueryClient>, record: McpServerRecord) {
  qc.setQueryData<McpTreeResponse>(queryKeys.mcpTree, (prev) =>
    patchServerStatusInTree(prev, record.id, record.status),
  );
  qc.setQueryData<McpServerRecord[]>(queryKeys.mcpServers, (prev) =>
    prev?.map((s) => (s.id === record.id ? { ...s, status: record.status } : s)),
  );
  void qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
  void qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
}

export function useMcpServerActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.mcpServers });
    void qc.invalidateQueries({ queryKey: queryKeys.mcpTree });
  };
  return {
    start: useMutation({
      mutationFn: mcpServersApi.start,
      onSuccess: (record) => syncServerStatus(qc, record),
    }),
    stop: useMutation({
      mutationFn: mcpServersApi.stop,
      onSuccess: (record) => syncServerStatus(qc, record),
    }),
    remove: useMutation({
      mutationFn: mcpServersApi.remove,
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string; name?: string; description?: string }) =>
        mcpServersApi.update(id, body),
      onSuccess: invalidate,
    }),
  };
}
