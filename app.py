import streamlit as st
import pandas as pd
from database import DatabaseManager
import plotly.express as px

# 页面配置
st.set_page_config(page_title="野外考察数据管理系统", layout="wide")

# 初始化数据库管理器
db = DatabaseManager()

st.title("🌐 野外考察传感器数据管理系统")
st.markdown("---")

# 侧边栏：操作面板
st.sidebar.header("数据录入")
with st.sidebar.form("add_data_form"):
    device_id = st.text_input("设备 ID", "DEV-001")
    col1, col2 = st.columns(2)
    with col1:
        temp = st.number_input("温度 (°C)", value=25.0)
        hum = st.number_input("湿度 (%)", value=50.0)
        pm25 = st.number_input("PM2.5", value=10.0)
    with col2:
        press = st.number_input("气压 (hPa)", value=1013.25)
        dew_pt = st.number_input("露点温度 (°C)", value=None, format="%.1f", placeholder="留空自动计算")
        hi = st.number_input("热指数 (°C)", value=None, format="%.1f", placeholder="留空自动计算")
        ws = st.number_input("风速 (m/s)", value=None, format="%.1f", placeholder="留空")
        wd = st.number_input("风向 (°)", value=None, min_value=0, max_value=360, format="%.0f", placeholder="留空")
    with col2:
        lat = st.number_input("纬度", value=31.23, format="%.6f")
        lon = st.number_input("经度", value=121.47, format="%.6f")
    
    submit_button = st.form_submit_button("保存数据")
    if submit_button:
        db.add_record(device_id, temp, hum, pm25, press, dew_pt if dew_pt != 0 else None, hi if hi != 0 else None, ws if ws != 0 else None, wd if wd != 0 else None, lat, lon)
        st.sidebar.success("记录已保存！")
        st.rerun()

# 主界面：数据概览
stats = db.get_stats()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("总记录数", f"{int(stats['count'])}")
c2.metric("平均温度", f"{stats['avg_temp']:.2f} °C")
c3.metric("平均湿度", f"{stats['avg_hum']:.2f} %")
c4.metric("平均气压", f"{stats.get('avg_pressure', 0):.1f} hPa")
c5.metric("平均露点", f"{stats.get('avg_dew_point', 0):.1f} °C")

# 获取数据
df = db.fetch_all_data()

# 数据展示与地图
tab1, tab2, tab3 = st.tabs(["📊 数据看板", "🗄️ 数据详情", "📍 地理分布"])

with tab1:
    if not df.empty:
        st.subheader("环境参数趋势")
        # 时间序列图
        fig = px.line(df, x="timestamp", y=["temperature", "humidity"], 
                     title="温度与湿度变化趋势", labels={"value": "数值", "timestamp": "时间"})
        st.plotly_chart(fig, use_container_width=True)
        
        # PM2.5 分布
        fig_pm = px.bar(df, x="timestamp", y="pm25", color="device_id", title="PM2.5 历史记录")
        st.plotly_chart(fig_pm, use_container_width=True)
    else:
        st.info("暂无数据，请在侧边栏添加。")

with tab2:
    st.subheader("历史记录明细")
    if not df.empty:
        # 允许删除
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="data_editor")
        st.caption("注：目前界面编辑仅作展示，删除操作请使用 ID。")
        
        del_id = st.number_input("要删除的记录 ID", min_value=0, step=1)
        if st.button("确认删除"):
            db.delete_record(del_id)
            st.success(f"ID {del_id} 已删除")
            st.rerun()
    else:
        st.write("表格为空")

with tab3:
    st.subheader("考察点地图")
    if not df.empty:
        # 过滤掉经纬度为0的数据
        map_df = df[(df['latitude'] != 0) & (df['longitude'] != 0)]
        if not map_df.empty:
            st.map(map_df)
        else:
            st.warning("地理位置数据无效。")
    else:
        st.write("暂无地理数据。")

# 页脚
st.markdown("---")
st.caption("MIS Field Survey System v1.0")
