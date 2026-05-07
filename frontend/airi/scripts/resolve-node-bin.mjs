#!/usr/bin/env node

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

import { createRequire } from 'node:module'

const [, , packageName, binPath, startDir = process.cwd()] = process.argv

if (!packageName || !binPath) {
  console.error('Usage: resolve-node-bin.mjs <package-name> <bin-path> [start-dir]')
  process.exit(2)
}

const requireFromStart = createRequire(path.join(path.resolve(startDir), 'package.json'))
const packageJsonPath = requireFromStart.resolve(`${packageName}/package.json`)
const resolvedBinPath = path.join(path.dirname(packageJsonPath), binPath)

if (!fs.existsSync(resolvedBinPath)) {
  console.error(`Resolved bin does not exist: ${resolvedBinPath}`)
  process.exit(1)
}

console.info(resolvedBinPath)
