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
        <el-form-item label="纬度">
          <el-input-number v-model="form.latitude" :precision="6" style="width: 100%" />
        </el-form-item>
        <el-form-item label="经度">
          <el-input-number v-model="form.longitude" :precision="6" style="width: 100%" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submitData" style="width: 100%">保存数据</el-button>
        </el-form-item>
      </el-form>
    </el-aside>

    <el-main>
      <h1>🌐 野外考察传感器数据管理系统</h1>
      <el-divider />

      <el-row :gutter="20" class="stats-row">
        <el-col :span="8">
          <el-card shadow="hover">
            <div class="stat-title">总记录数</div>
            <div class="stat-value">{{ stats.count }}</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover">
            <div class="stat-title">平均温度</div>
            <div class="stat-value">{{ stats.avg_temp }} °C</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="hover">
            <div class="stat-title">平均湿度</div>
            <div class="stat-value">{{ stats.avg_hum }} %</div>
          </el-card>
        </el-col>
      </el-row>

      <el-tabs v-model="activeTab" class="main-tabs" @tab-click="handleTabClick">
        <el-tab-pane label="📊 数据看板" name="dashboard">
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

const API_BASE = "http://localhost:8000/api"
const activeTab = ref('dashboard')
const stats = ref({ count: 0, avg_temp: 0, avg_hum: 0 })
const tableData = ref([])
const form = ref({ device_id: 'DEV-001', temperature: 25.0, humidity: 50.0, pm25: 10.0, pressure: 1013.25, latitude: 31.23, longitude: 121.47 })

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
  chart.setOption({
    title: { text: '传感器数据趋势' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: sortedData.map(item => item.timestamp.split(' ')[1] || item.timestamp) },
    yAxis: [{ type: 'value', name: '温度 (°C)' }, { type: 'value', name: '湿度 (%)' }],
    series: [
      { name: '温度', type: 'line', data: sortedData.map(item => item.temperature) },
      { name: '湿度', type: 'line', yAxisIndex: 1, data: sortedData.map(item => item.humidity) }
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
      const marker = new AMapInstance.Marker({ position: [item.longitude, item.latitude], title: item.device_id })
      marker.on('click', () => {
        const info = `<div>设备: ${item.device_id}<br>温度: ${item.temperature}</div>`
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
  const [dataRes, statsRes] = await Promise.all([axios.get(`${API_BASE}/data`), axios.get(`${API_BASE}/stats`)])
  tableData.value = dataRes.data
  stats.value = statsRes.data
  if (map) updateMarkers()
  if (chart) updateChart()
}

const submitData = async () => {
  await axios.post(`${API_BASE}/data`, form.value)
  ElMessage.success('保存成功')
  fetchData()
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
.el-aside { background: #fff; padding: 20px; border-right: 1px solid #dcdfe6; }
.main-tabs { background: #fff; padding: 20px; border-radius: 8px; }
</style>
