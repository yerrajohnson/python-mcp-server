import { Box, Grid, Typography } from '@mui/material';
import { useMemo, useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { specsApi } from '../api/client';
import { EndpointPanel } from '../components/mcp/EndpointPanel';
import { GenerationSummary } from '../components/mcp/GenerationSummary';
import { SpecSelector } from '../components/mcp/SpecSelector';
import { useSpecifications } from '../hooks/useSpecs';

export function McpServersPage() {
  const { data: specs = [] } = useSpecifications();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [endpoints, setEndpoints] = useState<Record<string, Set<string>>>({});

  const selectedIds = Array.from(selected);

  const detailQueries = useQueries({
    queries: selectedIds.map((id) => ({
      queryKey: ['specification', id],
      queryFn: () => specsApi.get(id),
    })),
  });

  const authLabels = useMemo(() => {
    const labels = new Set<string>();
    detailQueries.forEach((q) => {
      q.data?.parsed?.auth_schemes.forEach((a) => labels.add(a.type));
    });
    return Array.from(labels);
  }, [detailQueries]);

  const toggleSpec = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        setEndpoints((e) => {
          const copy = { ...e };
          delete copy[id];
          return copy;
        });
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleEndpoint = (specId: string, key: string) => {
    setEndpoints((prev) => {
      const set = new Set(prev[specId] ?? []);
      if (set.has(key)) set.delete(key);
      else set.add(key);
      return { ...prev, [specId]: set };
    });
  };

  const selectAll = (specId: string, keys: string[], select: boolean) => {
    setEndpoints((prev) => ({
      ...prev,
      [specId]: select ? new Set(keys) : new Set(),
    }));
  };

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        MCP Servers
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Select specifications and endpoints, then generate a downloadable MCP server.
      </Typography>

      <Grid container spacing={2} sx={{ minHeight: 560 }}>
        <Grid size={{ xs: 12, md: 3 }}>
          <SpecSelector specs={specs} selected={selected} onToggle={toggleSpec} />
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <EndpointPanel
            selectedSpecIds={selectedIds}
            selectedEndpoints={endpoints}
            onToggleEndpoint={toggleEndpoint}
            onSelectAll={selectAll}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 4 }}>
          <GenerationSummary
            selectedSpecIds={selectedIds}
            selectedEndpoints={endpoints}
            authLabels={authLabels}
          />
        </Grid>
      </Grid>
    </Box>
  );
}
