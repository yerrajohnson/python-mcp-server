import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useMemo, useState } from 'react';
import {
  useGroupEndpoints,
  useSpecification,
  useSpecifications,
  useWizardGenerate,
  useWizardSave,
} from '../../hooks/useSpecs';
import { specsApi } from '../../api/client';
import {
  endpointKey,
  type GeneratedServerPreview,
  type LogicalGroup,
  type SpecificationSummary,
} from '../../types';

const STEPS = [
  'Choose Specification',
  'Choose Endpoints',
  'Logical Groups',
  'Generate MCP Servers',
  'Review & Save',
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function GenerateWizard({ open, onClose }: Props) {
  const [step, setStep] = useState(0);
  const [specId, setSpecId] = useState<string | null>(null);
  const [searchSpec, setSearchSpec] = useState('');
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [endpointSearch, setEndpointSearch] = useState('');
  const [expandedTags, setExpandedTags] = useState<Record<string, boolean>>({});
  const [groups, setGroups] = useState<LogicalGroup[]>([]);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [servers, setServers] = useState<GeneratedServerPreview[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: specs = [] } = useSpecifications();
  const { data: specDetail } = useSpecification(specId);
  const groupMutation = useGroupEndpoints();
  const generateMutation = useWizardGenerate();
  const saveMutation = useWizardSave();

  const filteredSpecs = useMemo(() => {
    const q = searchSpec.toLowerCase();
    return specs.filter(
      (s) =>
        (s.status === 'parsed' || s.status === 'generated' || s.status === 'uploaded') &&
        (!q || s.name.toLowerCase().includes(q) || s.version.toLowerCase().includes(q)),
    );
  }, [specs, searchSpec]);

  const authLabel = useMemo(() => {
    const types = specDetail?.parsed?.auth_schemes?.map((a) => a.type) ?? [];
    return types.length ? types.join(', ') : 'none';
  }, [specDetail]);

  const endpointsByTag = useMemo(() => {
    const map: Record<string, typeof endpoints> = {};
    const endpoints = specDetail?.parsed?.endpoints ?? [];
    const q = endpointSearch.toLowerCase();
    for (const ep of endpoints) {
      if (
        q &&
        !ep.path.toLowerCase().includes(q) &&
        !(ep.summary ?? '').toLowerCase().includes(q) &&
        !(ep.tool_name ?? '').toLowerCase().includes(q)
      ) {
        continue;
      }
      const tag = ep.tags[0] || 'default';
      (map[tag] ??= []).push(ep);
    }
    return map;
  }, [specDetail, endpointSearch]);

  const reset = () => {
    setStep(0);
    setSpecId(null);
    setSearchSpec('');
    setSelectedKeys(new Set());
    setEndpointSearch('');
    setGroups([]);
    setBatchId(null);
    setServers([]);
    setError(null);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const ensureParsed = async (id: string) => {
    const current = await specsApi.get(id);
    if (!current.parsed) {
      const parsed = await specsApi.parse(id);
      if (parsed.status === 'parse_error') {
        throw new Error(parsed.error_message || 'Failed to parse specification');
      }
    }
  };

  const goNextFromSpec = async () => {
    if (!specId) return;
    setError(null);
    try {
      await ensureParsed(specId);
      setSelectedKeys(new Set());
      setStep(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load endpoints');
    }
  };

  const goGenerateGroups = async () => {
    if (!specId || selectedKeys.size === 0) return;
    setError(null);
    try {
      const res = await groupMutation.mutateAsync({
        specId,
        keys: Array.from(selectedKeys),
      });
      setGroups(res.groups);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Grouping failed');
    }
  };

  const goGenerateServers = async () => {
    if (!specId || groups.length === 0) return;
    setError(null);
    try {
      const res = await generateMutation.mutateAsync({ specId, groups });
      setBatchId(res.batch_id);
      setServers(res.servers);
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed');
    }
  };

  const goReview = () => setStep(4);

  const handleSave = async () => {
    if (!batchId) return;
    setError(null);
    try {
      await saveMutation.mutateAsync({ batchId, servers });
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    }
  };

  const toggleKey = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const selectTag = (tag: string, select: boolean) => {
    const eps = endpointsByTag[tag] ?? [];
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      for (const ep of eps) {
        const key = endpointKey(ep);
        if (select) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  };

  const allEndpointKeys = Object.values(endpointsByTag)
    .flat()
    .map(endpointKey);

  const renameGroup = (id: string, name: string) => {
    setGroups((prev) => prev.map((g) => (g.id === id ? { ...g, name } : g)));
  };

  const busy =
    groupMutation.isPending || generateMutation.isPending || saveMutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="md">
      <DialogTitle>Generate MCP Servers — Step {step + 1} of {STEPS.length}</DialogTitle>
      <DialogContent dividers>
        <Stepper activeStep={step} alternativeLabel sx={{ mb: 3 }}>
          {STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {busy && <LinearProgress sx={{ mb: 2 }} />}

        {step === 0 && (
          <StepChooseSpec
            specs={filteredSpecs}
            selectedId={specId}
            search={searchSpec}
            onSearch={setSearchSpec}
            onSelect={setSpecId}
          />
        )}

        {step === 1 && (
          <StepChooseEndpoints
            authLabel={authLabel}
            byTag={endpointsByTag}
            selectedKeys={selectedKeys}
            search={endpointSearch}
            expanded={expandedTags}
            onSearch={setEndpointSearch}
            onToggle={toggleKey}
            onSelectAll={(select) =>
              setSelectedKeys(select ? new Set(allEndpointKeys) : new Set())
            }
            onSelectTag={selectTag}
            onExpand={(tag) =>
              setExpandedTags((prev) => ({ ...prev, [tag]: !(prev[tag] ?? true) }))
            }
          />
        )}

        {step === 2 && (
          <StepLogicalGroups groups={groups} onRename={renameGroup} />
        )}

        {step === 3 && <StepGeneratedServers servers={servers} />}

        {step === 4 && (
          <StepReview
            specName={specDetail?.parsed?.info.title ?? specDetail?.name ?? '—'}
            endpointCount={selectedKeys.size}
            groupCount={groups.length}
            servers={servers}
          />
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2, justifyContent: 'space-between' }}>
        <Button onClick={handleClose} disabled={busy}>
          Cancel
        </Button>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {step > 0 && (
            <Button onClick={() => setStep((s) => s - 1)} disabled={busy}>
              Previous
            </Button>
          )}
          {step === 0 && (
            <Button variant="contained" disabled={!specId || busy} onClick={() => void goNextFromSpec()}>
              Next
            </Button>
          )}
          {step === 1 && (
            <Button
              variant="contained"
              disabled={selectedKeys.size === 0 || busy}
              onClick={() => void goGenerateGroups()}
            >
              Generate Logical Groups
            </Button>
          )}
          {step === 2 && (
            <Button
              variant="contained"
              disabled={groups.length === 0 || busy}
              onClick={() => void goGenerateServers()}
              startIcon={generateMutation.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              Generate MCP Servers
            </Button>
          )}
          {step === 3 && (
            <Button variant="contained" onClick={goReview} disabled={busy || servers.length === 0}>
              Next
            </Button>
          )}
          {step === 4 && (
            <Button
              variant="contained"
              onClick={() => void handleSave()}
              disabled={busy || !batchId}
              startIcon={saveMutation.isPending ? <CircularProgress size={16} color="inherit" /> : undefined}
            >
              Save
            </Button>
          )}
        </Box>
      </DialogActions>
    </Dialog>
  );
}

function StepChooseSpec({
  specs,
  selectedId,
  search,
  onSearch,
  onSelect,
}: {
  specs: SpecificationSummary[];
  selectedId: string | null;
  search: string;
  onSearch: (v: string) => void;
  onSelect: (id: string) => void;
}) {
  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Choose an uploaded OpenAPI specification. You will then select endpoints and generate MCP servers.
      </Typography>
      <TextField
        fullWidth
        size="small"
        placeholder="Search specifications…"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        sx={{ mb: 2 }}
      />
      <Paper variant="outlined" sx={{ maxHeight: 360, overflow: 'auto' }}>
        <List dense>
          {specs.map((s) => (
            <ListItemButton
              key={s.id}
              selected={selectedId === s.id}
              onClick={() => onSelect(s.id)}
            >
              <ListItemText
                primary={s.name}
                secondary={`v${s.version} · ${s.status} · ${new Date(s.upload_date).toLocaleString()}`}
              />
            </ListItemButton>
          ))}
          {!specs.length && (
            <Box sx={{ p: 2 }}>
              <Typography color="text.secondary">No specifications found. Upload one in the Specs tab first.</Typography>
            </Box>
          )}
        </List>
      </Paper>
    </Box>
  );
}

function StepChooseEndpoints({
  authLabel,
  byTag,
  selectedKeys,
  search,
  expanded,
  onSearch,
  onToggle,
  onSelectAll,
  onSelectTag,
  onExpand,
}: {
  authLabel: string;
  byTag: Record<string, Array<{ method: string; path: string; summary?: string | null; tool_name?: string | null }>>;
  selectedKeys: Set<string>;
  search: string;
  expanded: Record<string, boolean>;
  onSearch: (v: string) => void;
  onToggle: (key: string) => void;
  onSelectAll: (select: boolean) => void;
  onSelectTag: (tag: string, select: boolean) => void;
  onExpand: (tag: string) => void;
}) {
  const total = Object.values(byTag).flat().length;
  return (
    <Box>
      <Typography sx={{ mb: 1 }}>
        Authentication detected: <Chip size="small" label={authLabel} />
      </Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2, alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder="Search endpoints…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          sx={{ flex: 1, minWidth: 200 }}
        />
        <Button size="small" onClick={() => onSelectAll(true)}>
          Select All ({total})
        </Button>
        <Button size="small" onClick={() => onSelectAll(false)}>
          Deselect All
        </Button>
      </Box>
      <Box sx={{ maxHeight: 380, overflow: 'auto' }}>
        {Object.entries(byTag).map(([tag, eps]) => {
          const open = expanded[tag] ?? true;
          const selectedCount = eps.filter((ep) => selectedKeys.has(endpointKey(ep))).length;
          return (
            <Paper key={tag} variant="outlined" sx={{ mb: 1, p: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <IconButton size="small" onClick={() => onExpand(tag)}>
                  {open ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
                <Typography sx={{ fontWeight: 600, flex: 1 }}>
                  {tag} ({selectedCount}/{eps.length})
                </Typography>
                <Button size="small" onClick={() => onSelectTag(tag, true)}>
                  Select tag
                </Button>
                <Button size="small" onClick={() => onSelectTag(tag, false)}>
                  Clear
                </Button>
              </Box>
              <Collapse in={open}>
                {eps.map((ep) => {
                  const key = endpointKey(ep);
                  return (
                    <FormControlLabel
                      key={key}
                      sx={{ display: 'flex', ml: 1 }}
                      control={
                        <Checkbox
                          size="small"
                          checked={selectedKeys.has(key)}
                          onChange={() => onToggle(key)}
                        />
                      }
                      label={
                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                          <Chip label={ep.method} size="small" sx={{ minWidth: 56 }} />
                          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                            {ep.path}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            {ep.summary || ep.tool_name}
                          </Typography>
                        </Box>
                      }
                    />
                  );
                })}
              </Collapse>
            </Paper>
          );
        })}
      </Box>
    </Box>
  );
}

function StepLogicalGroups({
  groups,
  onRename,
}: {
  groups: LogicalGroup[];
  onRename: (id: string, name: string) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(groups[0]?.id ?? null);
  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Review logical groups. Rename groups before generating MCP servers. Each group becomes one MCP server.
      </Typography>
      {groups.map((g) => (
        <Paper key={g.id} variant="outlined" sx={{ mb: 1, p: 1.5 }}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
            <TextField
              size="small"
              value={g.name}
              onChange={(e) => onRename(g.id, e.target.value)}
              sx={{ flex: 1 }}
            />
            <Chip size="small" label={`${g.endpoints.length} endpoints`} />
            <IconButton size="small" onClick={() => setOpenId(openId === g.id ? null : g.id)}>
              {openId === g.id ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            </IconButton>
          </Box>
          {g.description && (
            <Typography variant="caption" color="text.secondary">
              {g.description}
            </Typography>
          )}
          <Collapse in={openId === g.id}>
            <Box sx={{ mt: 1 }}>
              {g.endpoints.map((ep) => (
                <Box key={ep.key} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.5 }}>
                  <Chip label={ep.method} size="small" />
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                    {ep.path}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {ep.summary || ep.tool_name}
                  </Typography>
                </Box>
              ))}
            </Box>
          </Collapse>
        </Paper>
      ))}
    </Box>
  );
}

function StepGeneratedServers({ servers }: { servers: GeneratedServerPreview[] }) {
  return (
    <Box>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Generated {servers.length} MCP server(s). Review tools and URLs, then continue.
      </Typography>
      {servers.map((s) => (
        <Paper key={s.temp_id} variant="outlined" sx={{ p: 2, mb: 1.5 }}>
          <Typography sx={{ fontWeight: 700 }}>{s.name}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {s.description}
          </Typography>
          <Typography variant="body2">
            <strong>URL:</strong>{' '}
            <Box component="span" sx={{ fontFamily: 'monospace' }}>
              {s.server_url}
            </Box>
          </Typography>
          <Typography variant="body2">
            <strong>Auth:</strong> {s.authentication.join(', ') || 'none'}
          </Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>Tools:</strong> {s.tool_count}
          </Typography>
          {s.tools.map((t) => (
            <Box key={t.name} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.25 }}>
              <Chip label={t.method} size="small" color="success" />
              <Typography variant="body2">{t.name}</Typography>
            </Box>
          ))}
        </Paper>
      ))}
    </Box>
  );
}

function StepReview({
  specName,
  endpointCount,
  groupCount,
  servers,
}: {
  specName: string;
  endpointCount: number;
  groupCount: number;
  servers: GeneratedServerPreview[];
}) {
  return (
    <Stack spacing={1}>
      <Typography>
        <strong>Specification:</strong> {specName}
      </Typography>
      <Typography>
        <strong>Selected endpoints:</strong> {endpointCount}
      </Typography>
      <Typography>
        <strong>Logical groups:</strong> {groupCount}
      </Typography>
      <Typography>
        <strong>MCP servers:</strong> {servers.length}
      </Typography>
      {servers.map((s) => (
        <Paper key={s.temp_id} variant="outlined" sx={{ p: 1.5 }}>
          <Typography sx={{ fontWeight: 600 }}>{s.name}</Typography>
          <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
            {s.server_url}
          </Typography>
          <Typography variant="body2">
            {s.tool_count} tools · auth: {s.authentication.join(', ') || 'none'}
          </Typography>
        </Paper>
      ))}
    </Stack>
  );
}
