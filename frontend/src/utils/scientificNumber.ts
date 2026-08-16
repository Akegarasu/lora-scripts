const DECIMAL_NUMBER_PATTERN = /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?$/

interface DecimalParts {
  negative: boolean
  integer: string
  fraction: string
  exponent: number
}

export type NumericInputValidation =
  | { status: 'empty' }
  | { status: 'invalid'; message: string }
  | { status: 'valid'; value: number }

export interface AlternateNotation {
  label: '小数' | '科学计数法'
  value: string
}

function decimalParts(raw: string): DecimalParts | null {
  const match = raw.trim().match(DECIMAL_NUMBER_PATTERN)
  if (!match) return null

  const hasInteger = match[2] !== undefined
  const exponent = Number(match[5] || 0)
  if (!Number.isSafeInteger(exponent)) return null

  return {
    negative: match[1] === '-',
    integer: hasInteger ? match[2] : '0',
    fraction: hasInteger ? (match[3] || '') : match[4],
    exponent,
  }
}

function hasNonZeroSignificand(parts: DecimalParts) {
  return /[1-9]/.test(`${parts.integer}${parts.fraction}`)
}

function normalizedDecimal(raw: string): string | null {
  const parts = decimalParts(raw)
  if (!parts) return null

  const digits = `${parts.integer}${parts.fraction}`
  const decimalPosition = parts.integer.length + parts.exponent
  let expanded: string

  if (decimalPosition <= 0) {
    expanded = `0.${'0'.repeat(-decimalPosition)}${digits}`
  } else if (decimalPosition >= digits.length) {
    expanded = `${digits}${'0'.repeat(decimalPosition - digits.length)}`
  } else {
    expanded = `${digits.slice(0, decimalPosition)}.${digits.slice(decimalPosition)}`
  }

  const [rawInteger, rawFraction = ''] = expanded.split('.')
  const integer = rawInteger.replace(/^0+(?=\d)/, '') || '0'
  const fraction = rawFraction.replace(/0+$/, '')
  const magnitude = fraction ? `${integer}.${fraction}` : integer
  const sign = parts.negative && hasNonZeroSignificand(parts) ? '-' : ''
  return `${sign}${magnitude}`
}

export function toScientificNotation(raw: string): string | null {
  const expanded = normalizedDecimal(raw)
  if (!expanded) return null

  const negative = expanded.startsWith('-')
  const unsigned = negative ? expanded.slice(1) : expanded
  const [integer, fraction = ''] = unsigned.split('.')
  const digits = `${integer}${fraction}`
  const firstNonZero = digits.search(/[1-9]/)
  if (firstNonZero === -1) return '0e0'

  const exponent = integer.length - firstNonZero - 1
  const significant = digits.slice(firstNonZero).replace(/0+$/, '')
  const coefficient = significant.length === 1
    ? significant
    : `${significant[0]}.${significant.slice(1)}`
  return `${negative ? '-' : ''}${coefficient}e${exponent}`
}

export function validateNumericInput(
  raw: string,
  options: { min?: number; max?: number } = {},
): NumericInputValidation {
  const text = raw.trim()
  if (!text) return { status: 'empty' }

  const parts = decimalParts(text)
  if (!parts) {
    return { status: 'invalid', message: '请输入有效数字，例如 0.00001 或 1e-5' }
  }

  const value = Number(text)
  if (!Number.isFinite(value)) {
    return { status: 'invalid', message: '数值超出可表示范围' }
  }
  if (value === 0 && hasNonZeroSignificand(parts)) {
    return { status: 'invalid', message: '数值过小，已超出可表示范围' }
  }
  if (options.min !== undefined && Number.isFinite(options.min) && value < options.min) {
    return { status: 'invalid', message: `不能小于 ${options.min}` }
  }
  if (options.max !== undefined && Number.isFinite(options.max) && value > options.max) {
    return { status: 'invalid', message: `不能大于 ${options.max}` }
  }

  return { status: 'valid', value }
}

export function alternateNotation(raw: string, value: number): AlternateNotation | null {
  if (/[eE]/.test(raw)) {
    const decimal = normalizedDecimal(raw)
    if (decimal && decimal.length <= 72) return { label: '小数', value: decimal }
    return null
  }

  const magnitude = Math.abs(value)
  if (magnitude === 0 || (magnitude >= 0.01 && magnitude < 1_000_000)) return null

  const scientific = toScientificNotation(raw)
  return scientific ? { label: '科学计数法', value: scientific } : null
}

export function modelNumberText(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return ''
    return Object.is(value, -0) ? '-0' : String(value)
  }
  if (typeof value === 'string' && validateNumericInput(value).status === 'valid') return value
  return ''
}
