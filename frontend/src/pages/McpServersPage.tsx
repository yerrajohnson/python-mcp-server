import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import DownloadIcon from '@mui/icons-material/Download';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import {
  Box,
  Button,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';
import { mcpServersApi } from '../api/client';
import {
  EmptyDetailPanel,
  ServerDetailPanel,
  SpecDetailPanel,
  ToolDetailPanel,
} from '../components/mcp/DetailPanels';
import { GenerateWizard } from '../components/mcp/GenerateWizard';
import { McpTreeNav } from '../components/mcp/McpTreeNav';
import { useMcpServerActions, useMcpTree } from '../hooks/useSpecs';
import type { TreeSelection, TreeServerNode, TreeSpecNode } from '../types';

/** Lightweight selection keys — always resolve live objects from tree data. */
type SelectionRef =
  | { type: 'spec'; specId: string }
  | { type: 'server'; specId: string; serverId: string }
  | { type: 'tool'; specId: string; serverId: string; toolId: string };

function toSelectionRef(sel: TreeSelection): SelectionRef {
  if (sel.type === 'spec') return { type: 'spec', specId: sel.spec.id };
  if (sel.type === 'server') {
    return { type: 'server', specId: sel.spec.id, serverId: sel.server.id };
  }
  return {
    type: 'tool',
    specId: sel.spec.id,
    serverId: sel.server.id,
    toolId: sel.tool.id,
  };
}

function resolveSelection(
  specs: TreeSpecNode[],
  ref: SelectionRef | null,
): TreeSelection | null {
  if (!ref) return null;
  const spec = specs.find((s) => s.id === ref.specId);
  if (!spec) return null;
  if (ref.type === 'spec') return { type: 'spec', spec };

  const server = spec.servers.find((s) => s.id === ref.serverId);
  if (!server) return null;
  if (ref.type === 'server') return { type: 'server', spec, server };

  const tool = server.tools.find((t) => t.id === ref.toolId);
  if (!tool) return null;
  return { type: 'tool', spec, server, tool };
}

export function McpServersPage() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selectionRef, setSelectionRef] = useState<SelectionRef | null>(null);
  const { data, isLoading, error } = useMcpTree();
  const actions = useMcpServerActions();

  const specs = data?.specifications ?? [];

  // Single source of truth: always derive UI selection from latest tree data
  const selection = useMemo(
    () => resolveSelection(specs, selectionRef),
    [specs, selectionRef],
  );

  const handleSelect = (sel: TreeSelection) => {
    setSelectionRef(toSelectionRef(sel));
  };

  const handleDeleteServer = (server: TreeServerNode) => {
    const toolLabel = server.tool_count === 1 ? '1 tool' : `${server.tool_count} tools`;
    if (
      !confirm(
        `Delete "${server.name}" and its ${toolLabel}? This cannot be undone.`,
      )
    ) {
      return;
    }
    actions.remove.mutate(server.id, {
      onSuccess: () => {
        if (
          selectionRef &&
          (selectionRef.type === 'server' || selectionRef.type === 'tool') &&
          selectionRef.serverId === server.id
        ) {
          setSelectionRef(null);
        }
      },
    });
  };

  const serverBusy =
    selection?.type === 'server' &&
    ((actions.start.isPending && actions.start.variables === selection.server.id) ||
      (actions.stop.isPending && actions.stop.variables === selection.server.id) ||
      (actions.remove.isPending && actions.remove.variables === selection.server.id));

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box>
          <Typography variant="h5" gutterBottom>
            MCP Servers
          </Typography>
          <Typography color="text.secondary">
            Explore specifications, servers, and tools in a hierarchical tree.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setWizardOpen(true)}>
          Generate MCP Server
        </Button>
      </Box>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {(error as Error).message}
        </Typography>
      )}

      <Paper
        variant="outlined"
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '340px 1fr' },
          minHeight: 560,
          overflow: 'hidden',
        }}
      >
        <Box sx={{ borderRight: { md: 1 }, borderColor: 'divider', bgcolor: 'background.paper' }}>
          <McpTreeNav
            specifications={specs}
            loading={isLoading}
            selection={selection}
            onSelect={handleSelect}
          />
        </Box>

        <Box sx={{ p: 3, overflow: 'auto', maxHeight: 'calc(100vh - 220px)' }}>
          {selection?.type === 'server' && (
            <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
              {selection.server.status === 'running' ? (
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  startIcon={<StopIcon />}
                  disabled={serverBusy}
                  onClick={() => actions.stop.mutate(selection.server.id)}
                >
                  Stop
                </Button>
              ) : (
                <Button
                  size="small"
                  variant="outlined"
                  color="success"
                  startIcon={<PlayArrowIcon />}
                  disabled={serverBusy}
                  onClick={() => actions.start.mutate(selection.server.id)}
                >
                  Start
                </Button>
              )}
              <Button
                size="small"
                variant="outlined"
                startIcon={<DownloadIcon />}
                disabled={serverBusy}
                onClick={() => window.open(mcpServersApi.downloadUrl(selection.server.id), '_blank')}
              >
                Download
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="error"
                startIcon={<DeleteIcon />}
                disabled={serverBusy}
                onClick={() => handleDeleteServer(selection.server)}
              >
                Delete
              </Button>
            </Stack>
          )}

          {!selection && <EmptyDetailPanel />}
          {selection?.type === 'spec' && <SpecDetailPanel spec={selection.spec} />}
          {selection?.type === 'server' && (
            <ServerDetailPanel spec={selection.spec} server={selection.server} />
          )}
          {selection?.type === 'tool' && (
            <ToolDetailPanel server={selection.server} tool={selection.tool} />
          )}
        </Box>
      </Paper>

      <GenerateWizard open={wizardOpen} onClose={() => setWizardOpen(false)} />
    </Box>
  );
}
