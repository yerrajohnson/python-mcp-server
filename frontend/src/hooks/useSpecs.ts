import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { generateApi, specsApi } from '../api/client';
import type { GenerateRequest } from '../types';

export const queryKeys = {
  specs: ['specifications'] as const,
  spec: (id: string) => ['specification', id] as const,
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
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.specs }),
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

export function useGenerateMcp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GenerateRequest) => generateApi.generate(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.specs }),
  });
}
