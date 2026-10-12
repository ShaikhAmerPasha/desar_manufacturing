import { execFileSync } from 'node:child_process'
import fs from 'node:fs'

export const CREDENTIALS_FILE = process.env.E2E_CREDS || '/tmp/desar_e2e_creds.json'
const BENCH_DIR = process.env.E2E_BENCH_DIR || '../..'
const SITE = process.env.E2E_SITE

export function runSeed(method) {
	if (!SITE) throw new Error('Set E2E_SITE to the (test) site name.')
	execFileSync('bench', ['--site', SITE, 'execute', `desar_manufacturing.e2e_seed.${method}`], { cwd: BENCH_DIR, stdio: 'inherit' })
}

export const credentials = () => JSON.parse(fs.readFileSync(CREDENTIALS_FILE, 'utf8'))
