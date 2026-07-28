import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FolderIcon from '@mui/icons-material/Folder';
import HubIcon from '@mui/icons-material/Hub';
import BuildIcon from '@mui/icons-material/Build';
import {
  Box,
  Chip,
  CircularProgress,
  Collapse,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useMemo, useState } from 'react';
import type { MouseEvent } from 'react';
import type { TreeSelection, TreeSpecNode } from '../../types';

const EXPANDED_KEY = 'mcp-tree-expanded';

function loadExpanded(): Set<string> {
  try {
    const raw = localStorage.getItem(EXPANDED_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function saveExpanded(set: Set<string>) {
  localStorage.setItem(EXPANDED_KEY, JSON.stringify(Array.from(set)));
}

interface Props {
  specifications: TreeSpecNode[];
  loading?: boolean;
  selection: TreeSelection | null;
  onSelect: (sel: TreeSelection) => void;
}

export function McpTreeNav({ specifications, loading, selection, onSelect }: Props) {
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Set<string>>(() => loadExpanded());

  useEffect(() => {
    saveExpanded(expanded);
  }, [expanded]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return specifications;

    return specifications
      .map((spec) => {
        const specMatch = spec.name.toLowerCase().includes(q);
        const servers = spec.servers
          .map((server) => {
            const serverMatch = server.name.toLowerCase().includes(q);
            const tools = server.tools.filter(
              (t) =>
                t.name.toLowerCase().includes(q) ||
                (t.path ?? '').toLowerCase().includes(q) ||
                (t.description ?? '').toLowerCase().includes(q),
            );
            if (specMatch || serverMatch || tools.length) {
              return {
                ...server,
                tools: specMatch || serverMatch ? server.tools : tools,
              };
            }
            return null;
          })
          .filter(Boolean) as TreeSpecNode['servers'];

        if (specMatch || servers.length) {
          return { ...spec, servers: specMatch ? spec.servers : servers };
        }
        return null;
      })
      .filter(Boolean) as TreeSpecNode[];
  }, [specifications, query]);

  const toggle = (id: string, e?: MouseEvent) => {
    e?.stopPropagation();
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const ensureExpanded = (...ids: string[]) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
  };

  const selectedKey =
    selection?.type === 'spec'
      ? `spec:${selection.spec.id}`
      : selection?.type === 'server'
        ? `server:${selection.server.id}`
        : selection?.type === 'tool'
          ? `tool:${selection.server.id}:${selection.tool.id}`
          : null;

  if (loading) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <TextField
        size="small"
        placeholder="Search specs, servers, tools…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        sx={{ m: 1.5, mb: 1 }}
      />
      <List dense sx={{ flex: 1, overflow: 'auto', py: 0 }}>
        {!filtered.length && (
          <Typography color="text.secondary" sx={{ px: 2, py: 1 }} variant="body2">
            No MCP servers yet. Generate one to populate the tree.
          </Typography>
        )}
        {filtered.map((spec) => {
          const specKey = `spec:${spec.id}`;
          const specOpen = expanded.has(specKey) || Boolean(query);
          return (
            <Box key={spec.id}>
              <ListItemButton
                selected={selectedKey === specKey}
                onClick={() => {
                  ensureExpanded(specKey);
                  onSelect({ type: 'spec', spec });
                }}
                sx={{ py: 0.75 }}
              >
                <IconButton size="small" onClick={(e) => toggle(specKey, e)} sx={{ mr: 0.5 }}>
                  {specOpen ? <ExpandMoreIcon fontSize="small" /> : <ChevronRightIcon fontSize="small" />}
                </IconButton>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  <FolderIcon fontSize="small" color="primary" />
                </ListItemIcon>
                <ListItemText
                  primary={spec.name}
                  secondary={`${spec.server_count} servers · ${spec.tool_count} tools`}
                  slotProps={{
                    primary: { sx: { fontWeight: 700, fontSize: 14 } },
                  }}
                />
              </ListItemButton>

              <Collapse in={specOpen} timeout="auto" unmountOnExit>
                {spec.servers.map((server) => {
                  const serverKey = `server:${server.id}`;
                  const serverOpen = expanded.has(serverKey) || Boolean(query);
                  return (
                    <Box key={server.id}>
                      <ListItemButton
                        selected={selectedKey === serverKey}
                        onClick={() => {
                          ensureExpanded(specKey, serverKey);
                          onSelect({ type: 'server', spec, server });
                        }}
                        sx={{ pl: 4, py: 0.5 }}
                      >
                        <IconButton size="small" onClick={(e) => toggle(serverKey, e)} sx={{ mr: 0.5 }}>
                          {serverOpen ? (
                            <ExpandMoreIcon fontSize="small" />
                          ) : (
                            <ChevronRightIcon fontSize="small" />
                          )}
                        </IconButton>
                        <ListItemIcon sx={{ minWidth: 28 }}>
                          <HubIcon fontSize="small" color="secondary" />
                        </ListItemIcon>
                        <ListItemText
                          primary={server.name}
                          secondary={
                            <Chip
                              size="small"
                              label={server.status}
                              color={server.status === 'running' ? 'success' : 'default'}
                              sx={{ height: 18, fontSize: 10, mt: 0.25 }}
                            />
                          }
                          slotProps={{
                            primary: { sx: { fontSize: 13, fontWeight: 600 } },
                          }}
                        />
                      </ListItemButton>

                      <Collapse in={serverOpen} timeout="auto" unmountOnExit>
                        {server.tools.map((tool) => {
                          const toolKey = `tool:${server.id}:${tool.id}`;
                          return (
                            <ListItemButton
                              key={toolKey}
                              selected={selectedKey === toolKey}
                              onClick={() => {
                                ensureExpanded(specKey, serverKey);
                                onSelect({ type: 'tool', spec, server, tool });
                              }}
                              sx={{ pl: 8, py: 0.35 }}
                            >
                              <ListItemIcon sx={{ minWidth: 28 }}>
                                <BuildIcon fontSize="small" />
                              </ListItemIcon>
                              <ListItemText
                                primary={tool.name}
                                secondary={tool.method ? `${tool.method} ${tool.path}` : undefined}
                                slotProps={{
                                  primary: { sx: { fontSize: 12.5 } },
                                  secondary: { sx: { fontSize: 11, fontFamily: 'monospace' } },
                                }}
                              />
                            </ListItemButton>
                          );
                        })}
                      </Collapse>
                    </Box>
                  );
                })}
              </Collapse>
              <Box sx={{ borderBottom: 1, borderColor: 'divider', mx: 1.5, my: 0.5 }} />
            </Box>
          );
        })}
      </List>
    </Box>
  );
}
