import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { api, isoLima } from '../api';
import { useEstado } from '../ctx';

echarts.use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

const SERIES = [
  { v: 'caudal/setpoint_pid', nombre: 'Setpoint', eje: 0, paso: true },
  { v: 'caudal/pv_pid', nombre: 'Caudal (PV)', eje: 0 },
  { v: 'caudal/caudalimetro', nombre: 'Caudalímetro', eje: 0 },
  { v: 'actuadores/variador_pct', nombre: 'Variador %', eje: 1 },
];

function css(nombre: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
}

export default function TendenciaPanel() {
  const { momento, tema } = useEstado();
  const div = useRef<HTMLDivElement>(null);
  const graf = useRef<echarts.ECharts | null>(null);
  const [ventana, setVentana] = useState(10);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!div.current) return;
    graf.current = echarts.init(div.current, undefined, { renderer: 'canvas' });
    const ro = new ResizeObserver(() => graf.current?.resize());
    ro.observe(div.current);
    return () => { ro.disconnect(); graf.current?.dispose(); };
  }, []);

  useEffect(() => {
    let vivo = true;
    async function cargar() {
      const centro = momento ? Date.parse(momento) : Date.now();
      const t0 = momento ? centro - (ventana * 60e3) / 2 : centro - ventana * 60e3;
      const t1 = momento ? centro + (ventana * 60e3) / 2 : centro;
      try {
        const h = await api.historial(SERIES.map((s) => s.v), isoLima(t0), isoLima(t1), 400);
        if (!vivo || !graf.current) return;
        setError(null);
        const col = [css('--c-sp'), css('--c-pv'), css('--c-q'), css('--c-var')];
        const texto = css('--txt-2');
        const rejilla = css('--borde');
        graf.current.setOption({
          animation: false,
          grid: { left: 44, right: 44, top: 34, bottom: 26 },
          legend: { top: 4, left: 8, itemWidth: 14, itemHeight: 3, textStyle: { color: texto, fontSize: 11 } },
          tooltip: { trigger: 'axis', valueFormatter: (v: number) => (v == null ? '—' : v.toFixed(2)) },
          xAxis: { type: 'time', min: t0, max: t1, axisLabel: { color: texto, fontSize: 10, hideOverlap: true },
            axisLine: { lineStyle: { color: rejilla } }, splitLine: { show: false } },
          yAxis: [
            { type: 'value', name: 'L/min', min: 0, nameTextStyle: { color: texto, fontSize: 10 },
              axisLabel: { color: texto, fontSize: 10 }, splitLine: { lineStyle: { color: rejilla } } },
            { type: 'value', name: '%', min: 0, max: 100, nameTextStyle: { color: texto, fontSize: 10 },
              axisLabel: { color: texto, fontSize: 10 }, splitLine: { show: false } },
          ],
          series: SERIES.map((s, i) => ({
            name: s.nombre, type: 'line', yAxisIndex: s.eje, showSymbol: false, step: s.paso ? 'end' : undefined,
            lineStyle: { width: s.v === 'caudal/pv_pid' ? 2 : 1.3, type: s.eje === 1 ? 'dashed' : 'solid', color: col[i] },
            itemStyle: { color: col[i] }, connectNulls: false,
            data: (h.series[s.v] ?? []).map(([t, v]) => [Date.parse(t), v]),
            markLine: i === 0 && momento ? { symbol: 'none', silent: true, label: { show: false },
              lineStyle: { color: css('--acento'), width: 1.5, type: 'solid' }, data: [{ xAxis: centro }] } : undefined,
          })),
        }, true);
      } catch (e) {
        if (vivo) setError(String(e));
      }
    }
    cargar();
    const intervalo = momento ? null : window.setInterval(cargar, 5000);
    return () => { vivo = false; if (intervalo) window.clearInterval(intervalo); };
  }, [momento, ventana, tema]);

  return (
    <div className="tend">
      <div className="tend-barra">
        {[5, 10, 30, 60].map((m) => (
          <button key={m} className={m === ventana ? 'on' : ''} onClick={() => setVentana(m)}>{m} min</button>
        ))}
        <span className="tend-nota">{momento ? 'centrado en el momento elegido' : 'últimos minutos · se actualiza cada 5 s'}</span>
      </div>
      {error && <div className="vacio">No se pudo leer el historial: {error}</div>}
      <div ref={div} className="tend-graf nodrag nowheel" />
    </div>
  );
}
