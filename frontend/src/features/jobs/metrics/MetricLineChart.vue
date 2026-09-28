<script setup lang="ts">
import { LineChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { MetricGroupId, DisplayMetricSeries } from './useMetricCurves'

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
])

const props = defineProps<{
  series: DisplayMetricSeries[]
  group: MetricGroupId
}>()

const chartElement = ref<HTMLDivElement | null>(null)
let chart: ReturnType<typeof echarts.init> | null = null
let resizeObserver: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null
let renderFrame = 0

const GROUP_LABELS: Record<MetricGroupId, string> = {
  loss: '损失',
  lr: '学习率',
  norm: '范数',
  other: '指标值',
}

function cssColor(name: string, fallback: string) {
  const element = chartElement.value
  if (!element) return fallback
  return getComputedStyle(element).getPropertyValue(name).trim() || fallback
}

function valueLabel(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  const absolute = Math.abs(value)
  if ((absolute > 0 && absolute < 0.0001) || absolute >= 100_000) return value.toExponential(4)
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 7 })
}

function tooltipValueLabel(value: unknown) {
  return valueLabel(Array.isArray(value) ? value[1] : value)
}

function renderChart() {
  const element = chartElement.value
  if (!element) return
  if (!chart) chart = echarts.init(element, undefined, { renderer: 'canvas' })

  const text = cssColor('--text-secondary', '#555552')
  const muted = cssColor('--text-muted', '#6f6f6b')
  const border = cssColor('--border-subtle', '#deded9')
  const surface = cssColor('--surface', '#ffffff')
  const brand = cssColor('--brand', '#242424')

  chart.setOption(
    {
      animation: false,
      color: [brand, '#4f78c4', '#d4873b', '#9a65c7', '#3d9ca8', '#c75870', '#7b8b3f'],
      textStyle: {
        color: text,
        fontSize: 13,
        fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif",
      },
      legend: {
        type: 'scroll',
        top: 2,
        left: 6,
        right: 6,
        itemWidth: 18,
        itemHeight: 3,
        textStyle: { color: text, fontSize: 12 },
        pageTextStyle: { color: muted, fontSize: 12 },
        pageIconColor: text,
        pageIconInactiveColor: border,
      },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: surface,
        borderColor: border,
        textStyle: { color: text, fontSize: 13 },
        valueFormatter: tooltipValueLabel,
      },
      grid: {
        top: 46,
        right: 22,
        bottom: 66,
        left: 24,
        containLabel: true,
      },
      xAxis: {
        type: 'value',
        name: '训练步',
        nameLocation: 'middle',
        nameGap: 30,
        nameTextStyle: { color: muted, fontSize: 12 },
        axisLine: { lineStyle: { color: border } },
        axisTick: { lineStyle: { color: border } },
        axisLabel: { color: muted, fontSize: 12, hideOverlap: true },
        splitLine: { show: false },
        min: 'dataMin',
        max: 'dataMax',
      },
      yAxis: {
        type: 'value',
        name: GROUP_LABELS[props.group],
        nameTextStyle: { color: muted, fontSize: 12 },
        scale: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: muted,
          fontSize: 12,
          formatter: (value: number) => valueLabel(value),
        },
        splitLine: { lineStyle: { color: border, opacity: 0.55 } },
      },
      dataZoom: [
        { type: 'inside', filterMode: 'none', throttle: 80 },
        {
          type: 'slider',
          height: 18,
          bottom: 8,
          borderColor: border,
          backgroundColor: surface,
          fillerColor: `${brand}2b`,
          dataBackground: {
            lineStyle: { color: muted },
            areaStyle: { color: `${brand}1f` },
          },
          selectedDataBackground: {
            lineStyle: { color: brand },
            areaStyle: { color: `${brand}38` },
          },
          handleStyle: { color: surface, borderColor: brand },
          moveHandleStyle: { color: brand, opacity: 0.65 },
          textStyle: { color: muted, fontSize: 12 },
        },
      ],
      series: props.series.map((item) => ({
        id: item.id,
        name: item.label,
        type: 'line',
        data: item.points.map((point) => [point.step, point.value]),
        showSymbol: false,
        symbol: 'none',
        sampling: 'lttb',
        connectNulls: false,
        smooth: item.derived ? 0.12 : false,
        lineStyle: {
          width: item.derived ? 2.1 : 1.55,
          type: item.derived ? 'dashed' : 'solid',
          opacity: item.derived ? 0.95 : 0.82,
        },
        emphasis: { focus: 'series', lineStyle: { width: 2.7 } },
      })),
    },
    { notMerge: true, lazyUpdate: true },
  )
}

function scheduleRender() {
  if (renderFrame) window.cancelAnimationFrame(renderFrame)
  renderFrame = window.requestAnimationFrame(() => {
    renderFrame = 0
    renderChart()
  })
}

onMounted(() => {
  renderChart()
  if (chartElement.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartElement.value)
  }
  themeObserver = new MutationObserver(scheduleRender)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})

watch(() => [props.series, props.group], scheduleRender, { deep: true })

onBeforeUnmount(() => {
  if (renderFrame) window.cancelAnimationFrame(renderFrame)
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div
    ref="chartElement"
    class="metric-chart"
    role="img"
    :aria-label="`${GROUP_LABELS[group]} 指标曲线，共 ${series.length} 条`"
  />
</template>

<style scoped>
.metric-chart {
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 310px;
}

@media (max-width: 640px) {
  .metric-chart {
    min-height: 300px;
  }
}
</style>
