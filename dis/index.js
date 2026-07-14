#!/usr/bin/env node

/**
 * Chief Of Staff - Gmail MCP Server Launcher
 * Launches the gmail-mcp-server via the compiled dist/index.js
 */

const { spawn } = require('child_process');
const path = require('path');

const serverPath = path.join(__dirname, '..', 'gmail-mcp-server', 'dist', 'index.js');

const server = spawn('node', [serverPath], {
  stdio: 'inherit',
  cwd: path.join(__dirname, '..', 'gmail-mcp-server'),
});

server.on('error', (err) => {
  console.error('Failed to start Gmail MCP server:', err.message);
  process.exit(1);
});

server.on('close', (code) => {
  process.exit(code ?? 0);
});

// Forward termination signals
process.on('SIGINT', () => server.kill('SIGINT'));
process.on('SIGTERM', () => server.kill('SIGTERM'));
process.on('exit', () => server.kill());
