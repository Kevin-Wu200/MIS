<template>
  <el-container class="layout-container">
    <el-aside width="35%">
      <div class="sidebar-header">
        <h3>数据录入</h3>
      </div>
      <el-form :model="form" label-width="80px" class="entry-form">
        <el-form-item label="设备 ID">
          <el-input v-model="form.device_id" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="温度">
              <el-input-number v-model="form.temperature" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="湿度">
              <el-input-number v-model="form.humidity" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="PM2.5">
          <el-input-number v-model="form.pm25" style="width: 100%" />
        </el-form-item>
        <el-form-item label="气压">
          <el-input-number v-model="form.pressure" style="width: 100%" />
        </el-form-item>
        <el-row :gutter="10">
          <el-col :span="12">
            <el-form-item label="风速(m/s)">
              <el-input-number v-model="form.wind_speed" :precision="1" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="风向(°)">
              <el-input-number v-model="form.wind_direction" :min="0" :max="360" :precision="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="纬度">
          <el-input-number v-model="form.latitude" :precision="6" style="width: 100%" />
        </el-form-item>
        <el-form-item label="经度">
          <el-input-number v-model="form.longitude" :precision="6" style="width: 100%" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="isSaving" @click="submitData" style="width: 100%">保存数据</el-button>
        </el-form-item>
      </el-form>
    </el-aside>

    <el-main>
      <h1>🌐 野外考察传感器数据管理系统</h1>
      <el-divider />

      <el-row :gutter="20" class="stats-row">
        <el-col :span="4">
          <el-card shadow="hover">
            <div class="stat-title">总记录数</div>
            <div class="stat-value">{{ stats.count }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <div class="stat-title">平均温度</div>
            <div class="stat-value">{{ stats.avg_temp }} °C</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <div class="stat-title">平均湿度</div>
            <div class="stat-value">{{ stats.avg_hum }} %</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <div class="stat-title">平均气压</div>
            <div class="stat-value">{{ stats.avg_pressure }} hPa</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover">
            <div class="stat-title">平均露点</div>
            <div class="stat-value">{{ stats.avg_dew_point }} °C</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="hover" :class="{ 'anomaly-card': stats.anomaly_count > 0 }">
            <div class="stat-title">AI 异常数</div>
            <div class="stat-value">{{ stats.anomaly_count }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-tabs v-model="activeTab" class="main-tabs" @tab-click="handleTabClick">
        <el-tab-pane label="📊 数据看板" name="dashboard">
          <el-alert
            class="ai-insight"
            :title="aiInsights.summary"
            :type="aiInsights.anomaly_count > 0 ? 'warning' : 'success'"
            :closable="false"
            show-icon
          >
            <template #default>
              <div class="insight-meta">
                异常记录 {{ aiInsights.anomaly_count }} 条，平均异常评分 {{ formatScore(aiInsights.avg_anomaly_score) }}
                <div v-if="aiInsights.time_dimension_alerts && aiInsights.time_dimension_alerts.length > 0" class="time-alerts">
                  <el-tag
                    v-for="(alert, idx) in aiInsights.time_dimension_alerts.slice(0, 5)"
                    :key="idx"
                    :type="alert.level === 'critical' ? 'danger' : 'warning'"
                    size="small"
                    style="margin: 2px"
                  >
                    {{ alert.message?.substring(0, 40) }}{{ alert.message?.length > 40 ? '...' : '' }}
                  </el-tag>
                </div>
              </div>
            </template>
          </el-alert>
          <div style="height: 450px; width: 100%" id="chart-container"></div>
        </el-tab-pane>

        <el-tab-pane label="🗄️ 数据详情" name="table">
          <el-table :data="tableData" style="width: 100%" height="500">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="timestamp" label="时间" width="180" />
            <el-table-column prop="device_id" label="设备 ID" width="120" />
            <el-table-column prop="temperature" label="温度" />
            <el-table-column prop="humidity" label="湿度" />
            <el-table-column prop="pm25" label="PM2.5" />
            <el-table-column prop="dew_point" label="露点" />
            <el-table-column prop="heat_index" label="热指数" />
            <el-table-column prop="wind_speed" label="风速" />
            <el-table-column label="AI 状态" width="130">
              <template #default="scope">
                <el-tag :type="scope.row.is_anomaly ? 'danger' : 'success'" effect="dark">
                  {{ scope.row.is_anomaly ? '异常' : '正常' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="异常评分" width="110">
              <template #default="scope">{{ formatScore(scope.row.anomaly_score) }}</template>
            </el-table-column>
            <el-table-column prop="ai_summary" label="AI 摘要" min-width="260" show-overflow-tooltip />
            <el-table-column label="操作" width="100">
              <template #default="scope">
                <el-button type="danger" size="small" @click="deleteRow(scope.row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="🗺️ 点位地理分布" name="mapShow">
          <div style="height: 500px; width: 100%; border-radius: 8px;" id="map-container"></div>
        </el-tab-pane>
      </el-tabs>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, onMounted, nextTick, onUnmounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import AMapLoader from '@amap/amap-jsapi-loader'

window._AMapSecurityConfig = { securityJsCode: 'df68efe4460053c483fbd6489b5603d0' }

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8080/api"
const activeTab = ref('dashboard')
const stats = ref({ count: 0, avg_temp: 0, avg_hum: 0, avg_pm25: 0, avg_pressure: 0, avg_dew_point: 0, avg_heat_index: 0, avg_wind_speed: 0, anomaly_count: 0 })
const aiInsights = ref({ summary: 'AI 洞察加载中...', anomaly_count: 0, avg_anomaly_score: 0, latest_anomaly: null, time_dimension_alerts: [] })
const tableData = ref([])
const form = ref({ device_id: 'DEV-001', temperature: 25.0, humidity: 50.0, pm25: 10.0, pressure: 1013.25, dew_point: null, heat_index: null, wind_speed: null, wind_direction: null, latitude: 31.23, longitude: 121.47 })
const isSaving = ref(false)

let map = null
let chart = null
let markers = []
let AMapInstance = null

const initChart = () => {
  if (chart) return
  const chartDom = document.getElementById('chart-container')
  if (!chartDom) return
  chart = echarts.init(chartDom)
  updateChart()
}

const updateChart = () => {
  if (!chart) return
  const sortedData = [...tableData.value].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
  const anomalyMarkPoints = sortedData
    .map((item, index) => item.is_anomaly ? { name: 'AI 异常', coord: [index, item.temperature], value: formatScore(item.anomaly_score) } : null)
    .filter(Boolean)
  chart.setOption({
    title: { text: '传感器数据趋势' },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const item = sortedData[params[0].dataIndex]
        const lines = params.map(p => `${p.marker}${p.seriesName}: ${p.value}`).join('<br>')
        const aiLine = item?.is_anomaly ? `<br><strong>AI 异常评分: ${formatScore(item.anomaly_score)}</strong>` : ''
        return `${item?.timestamp || ''}<br>${lines}${aiLine}`
      }
    },
    xAxis: { type: 'category', data: sortedData.map(item => item.timestamp.split(' ')[1] || item.timestamp) },
    yAxis: [{ type: 'value', name: '温度 (°C)' }, { type: 'value', name: '湿度 (%)' }],
    series: [
      {
        name: '温度',
        type: 'line',
        data: sortedData.map(item => item.temperature),
        markPoint: {
          symbolSize: 54,
          itemStyle: { color: '#d93025' },
          data: anomalyMarkPoints
        }
      },
      { name: '湿度', type: 'line', yAxisIndex: 1, data: sortedData.map(item => item.humidity) },
      { name: '气压', type: 'line', yAxisIndex: 0, data: sortedData.map(item => item.pressure), lineStyle: { type: 'dashed' }, itemStyle: { color: '#722ed1' } }
    ]
  })
}

const initMap = () => {
  if (map) return
  AMapLoader.load({ key: '281b1354a75838eafe420d43c823b708', version: '2.0' }).then((AMap) => {
    AMapInstance = AMap
    map = new AMap.Map('map-container', { zoom: 10, center: [121.47, 31.23] })
    updateMarkers()
  })
}

const updateMarkers = () => {
  if (!map || !AMapInstance) return
  markers.forEach(m => map.remove(m))
  markers = []
  tableData.value.forEach(item => {
    if (item.latitude && item.longitude) {
      const marker = new AMapInstance.Marker({
        position: [item.longitude, item.latitude],
        title: item.device_id,
        content: `<div class="${item.is_anomaly ? 'map-marker danger' : 'map-marker'}"></div>`,
        offset: new AMapInstance.Pixel(-8, -8)
      })
      marker.on('click', () => {
        const info = `<div>设备: ${item.device_id}<br>温度: ${item.temperature}<br>AI 状态: ${item.is_anomaly ? '异常' : '正常'}<br>评分: ${formatScore(item.anomaly_score)}</div>`
        new AMapInstance.InfoWindow({ content: info }).open(map, marker.getPosition())
      })

      map.add(marker)
      markers.push(marker)
    }
  })
}

const handleTabClick = (pane) => {
  if (pane.name === 'mapShow') nextTick(initMap)
  else if (pane.name === 'dashboard') nextTick(() => { initChart(); chart?.resize() })
}

const fetchData = async () => {
  try {
    const [dataRes, statsRes, insightsRes] = await Promise.all([
      axios.get(`${API_BASE}/data`),
      axios.get(`${API_BASE}/stats`),
      axios.get(`${API_BASE}/ai/insights`)
    ])
    tableData.value = dataRes.data
    stats.value = statsRes.data
    aiInsights.value = insightsRes.data
    if (map) updateMarkers()
    if (chart) updateChart()
  } catch (error) {
    ElMessage.error(`数据刷新失败：${error.response?.data?.detail || error.message}`)
    throw error
  }
}

const formatScore = (score) => Number(score || 0).toFixed(2)

const submitData = async () => {
  if (isSaving.value) return
  isSaving.value = true
  try {
    await axios.post(`${API_BASE}/data`, form.value)
    await fetchData()
    ElMessage.success('保存成功')
  } catch (error) {
    ElMessage.error(`保存失败：${error.response?.data?.detail || error.message}`)
  } finally {
    isSaving.value = false
  }
}

const deleteRow = async (id) => {
  await axios.delete(`${API_BASE}/data/${id}`)
  fetchData()
}

onMounted(() => { fetchData(); nextTick(() => { if (activeTab.value === 'dashboard') initChart() }) })
onUnmounted(() => { map?.destroy(); chart?.dispose() })
</script>

<style scoped>
.layout-container { height: 100vh; background-color: #f5f7fa; }
.el-aside { background: #fff; padding: 20px; border-right: 1px solid #dcdfe6; overflow-y: auto; }
.main-tabs { background: #fff; padding: 20px; border-radius: 8px; }
.stats-row { margin-bottom: 18px; }
.anomaly-card { border-color: #f56c6c; }
.ai-insight { margin-bottom: 16px; }
.insight-meta { margin-top: 6px; font-size: 13px; color: #606266; }
.time-alerts { margin-top: 8px; }
:global(.map-marker) {
  width: 16px;
  height: 16px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #1677ff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
}
:global(.map-marker.danger) {
  width: 20px;
  height: 20px;
  background: #d93025;
  box-shadow: 0 0 0 4px rgba(217, 48, 37, 0.2), 0 2px 8px rgba(0, 0, 0, 0.32);
}
</style>
