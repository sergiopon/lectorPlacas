import { spawn } from 'node:child_process'
import { rmSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '@playwright/test'
import { E2E_PORT } from '../playwright.config'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const STATE_PATH = 'e2e/.auth/state.json'

export default async function globalSetup(): Promise<() => Promise<void>> {
  const child = spawn('uv', ['run', 'lector-web', '--demo', '--no-browser', '--port', String(E2E_PORT)], {
    cwd: path.resolve(__dirname, '..', '..'),
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stderr = ''
  child.stderr.on('data', (chunk: Buffer) => {
    stderr += chunk.toString()
  })

  const url = await new Promise<string>((resolve, reject) => {
    let buffer = ''
    const timer = setTimeout(() => {
      child.kill()
      reject(new Error('lector-web no arrancó: ' + stderr))
    }, 30_000)
    child.on('error', (err) => {
      clearTimeout(timer)
      reject(err)
    })
    child.stdout.on('data', (chunk: Buffer) => {
      buffer += chunk.toString()
      for (const line of buffer.split('\n')) {
        if (line.startsWith('Abra: ')) {
          clearTimeout(timer)
          resolve(line.slice('Abra: '.length).trim())
          return
        }
      }
    })
  })

  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(url)
  await context.storageState({ path: STATE_PATH })
  await browser.close()

  return async () => {
    const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()))
    child.kill('SIGINT')
    const timer = setTimeout(() => child.kill('SIGKILL'), 10_000)
    await exited
    clearTimeout(timer)
    rmSync(STATE_PATH, { force: true })
  }
}
