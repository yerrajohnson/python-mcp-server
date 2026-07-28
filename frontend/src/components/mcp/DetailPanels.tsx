import {
  Box,
  Chip,
  Divider,
  Typography,
} from '@mui/material';
import type { ReactNode } from 'react';
import type { TreeServerNode, TreeSpecNode, TreeToolNode } from '../../types';
import { JsonViewer } from '../common/JsonViewer';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box sx={{ mb: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 1, fontSize: 16 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <Box sx={{ display: 'flex', gap: 1, py: 0.4 }}>
      <Typography variant="body2" sx={{ minWidth: 160, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ flex: 1 }}>
        {value || '—'}
      </Typography>
    </Box>
  );
}

export function SpecDetailPanel({ spec }: { spec: TreeSpecNode }) {
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        {spec.name}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        OpenAPI Specification
      </Typography>
      <Section title="Details">
        <Row label="Name" value={spec.name} />
        <Row label="Version" value={spec.version} />
        <Row label="Description" value={spec.description} />
        <Row label="OpenAPI Version" value={spec.openapi_version} />
        <Row
          label="Base URL(s)"
          value={
            spec.base_urls.length
              ? spec.base_urls.map((u) => (
                  <Typography key={u} sx={{ fontFamily: 'monospace', fontSize: 13 }}>
                    {u}
                  </Typography>
                ))
              : '—'
          }
        />
        <Row
          label="Authentication"
          value={
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {(spec.auth_types.length ? spec.auth_types : ['none']).map((a) => (
                <Chip key={a} size="small" label={a} />
              ))}
            </Box>
          }
        />
        <Row label="Endpoints" value={String(spec.endpoint_count)} />
        <Row label="MCP Servers" value={String(spec.server_count)} />
        <Row label="Total Tools" value={String(spec.tool_count)} />
        <Row
          label="Upload Date"
          value={spec.upload_date ? new Date(spec.upload_date).toLocaleString() : '—'}
        />
      </Section>
    </Box>
  );
}

export function ServerDetailPanel({
  spec,
  server,
}: {
  spec: TreeSpecNode;
  server: TreeServerNode;
}) {
  const categories = Array.from(new Set(server.tools.flatMap((t) => t.tags))).filter(Boolean);

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        {server.name}
      </Typography>
      <Chip
        size="small"
        label={server.status}
        color={server.status === 'running' ? 'success' : 'default'}
        sx={{ mb: 2, textTransform: 'capitalize' }}
      />

      <Section title="General Information">
        <Row label="Server Name" value={server.name} />
        <Row label="Description" value={server.description} />
        <Row label="Source Specification" value={spec.name} />
        <Row label="Server Version" value={server.version} />
        <Row label="Authentication" value={server.authentication.join(', ') || 'none'} />
        <Row
          label="Client auth"
          value="Set Authorization / X-API-Key on Postman requests to this MCP URL; they are forwarded to the upstream API when tools run."
        />
        <Row label="Number of Tools" value={String(server.tool_count)} />
        <Row label="Status" value={server.status} />
        <Row label="Logical Group" value={server.logical_group} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Endpoint Information">
        <Row
          label="MCP Endpoint URL"
          value={
            <Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>{server.endpoint}</Typography>
          }
        />
        <Row label="Transport Type" value={(server.transport || 'streamable-http').toUpperCase()} />
        <Row
          label="Health Status"
          value={server.status === 'running' ? 'Healthy / Running' : 'Stopped'}
        />
        <Row label="Created Date" value={new Date(server.created_date).toLocaleString()} />
        <Row label="Port" value="shared (single FastAPI app)" />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Tools Summary">
        <Row label="Total Tools" value={String(server.tool_count)} />
        <Row
          label="Tool Categories"
          value={
            categories.length ? (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {categories.map((c) => (
                  <Chip key={c} size="small" label={c} />
                ))}
              </Box>
            ) : (
              '—'
            )
          }
        />
        <Box sx={{ mt: 1 }}>
          {server.tools.map((t) => (
            <Box key={t.id} sx={{ display: 'flex', gap: 1, alignItems: 'center', py: 0.4 }}>
              {t.method && <Chip size="small" label={t.method} color="primary" />}
              <Typography variant="body2">{t.name}</Typography>
            </Box>
          ))}
        </Box>
      </Section>
    </Box>
  );
}

export function ToolDetailPanel({
  server,
  tool,
}: {
  server: TreeServerNode;
  tool: TreeToolNode;
}) {
  const pathParams = tool.parameters.filter((p) => p.location === 'path' || p.in === 'path');
  const queryParams = tool.parameters.filter((p) => p.location === 'query' || p.in === 'query');
  const headerParams = tool.parameters.filter((p) => p.location === 'header' || p.in === 'header');
  const primaryAuth = tool.auth_schemes[0] as Record<string, unknown> | undefined;

  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        {tool.name}
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Tool in {server.name}
      </Typography>

      <Section title="General Information">
        <Row label="Tool Name" value={tool.name} />
        <Row label="Description" value={tool.description} />
        <Row label="HTTP Method" value={tool.method} />
        <Row
          label="API Path"
          value={<Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>{tool.path}</Typography>}
        />
        <Row label="Operation ID" value={tool.operation_id} />
        <Row
          label="Tags"
          value={
            tool.tags.length ? (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {tool.tags.map((t) => (
                  <Chip key={t} size="small" label={t} />
                ))}
              </Box>
            ) : (
              '—'
            )
          }
        />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Authentication">
        <Row
          label="Authentication Type"
          value={
            primaryAuth?.type
              ? String(primaryAuth.type)
              : server.authentication.join(', ') || 'none'
          }
        />
        <Row label="Security Scheme" value={primaryAuth ? String(primaryAuth.name ?? '—') : '—'} />
        <Row
          label="API Key Location"
          value={primaryAuth?.location ? String(primaryAuth.location) : '—'}
        />
        <Row
          label="Required Scopes"
          value={
            tool.security.length
              ? JSON.stringify(tool.security)
              : '—'
          }
        />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Request Details">
        <Row
          label="Endpoint URL"
          value={
            <Typography sx={{ fontFamily: 'monospace', fontSize: 13 }}>
              {tool.url || `${tool.base_url ?? ''}${tool.path ?? ''}` || '—'}
            </Typography>
          }
        />
        <JsonViewer title="Headers (parameters)" value={headerParams} />
        <JsonViewer title="Query Parameters" value={queryParams} />
        <JsonViewer title="Path Parameters" value={pathParams} />
        <JsonViewer title="Request Body" value={tool.request_body ?? {}} />
        <JsonViewer title="Input Schema" value={tool.input_schema} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Response Details">
        <JsonViewer title="Responses / Status Codes" value={tool.responses} />
        <JsonViewer title="Output Schema" value={tool.output_schema} />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="MCP Information">
        <Row label="Generated Tool Name" value={tool.name} />
        <Row label="Tool Description" value={tool.description} />
        <JsonViewer title="MCP Input Schema" value={tool.input_schema} />
        <JsonViewer title="MCP Output Schema" value={tool.output_schema} />
      </Section>
    </Box>
  );
}

export function EmptyDetailPanel() {
  return (
    <Box
      sx={{
        height: '100%',
        minHeight: 360,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        color: 'text.secondary',
        textAlign: 'center',
        p: 4,
      }}
    >
      <HubIconPlaceholder />
      <Typography variant="h6" sx={{ mt: 1 }}>
        Select a server or tool to view details
      </Typography>
      <Typography variant="body2">
        Choose a specification, MCP server, or tool from the tree.
      </Typography>
    </Box>
  );
}

function HubIconPlaceholder() {
  return (
    <Box
      sx={{
        width: 72,
        height: 72,
        borderRadius: 2,
        bgcolor: 'action.hover',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 32,
      }}
    >
      ⌂
    </Box>
  );
}
