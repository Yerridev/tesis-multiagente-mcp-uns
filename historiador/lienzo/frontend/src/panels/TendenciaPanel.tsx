import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { apiEquipo, isoLima } from '../api';
import { useEstado } from '../ctx';

echarts.use([LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

function css(nombre: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
}

/** Tendencia del equipo: series, ejes y lineas de referencia vienen del registro (equipos.json). */
export default function TendenciaPanel() {
  const { equipo, momento, tema } = useEstado();
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
    if (!equipo) return;
    const cfg = equipo.tendencia;
    const api = apiEquipo(equipo.id);
    let vivo = true;
    async function cargar() {
      const centro = momento ? Date.parse(momento) : Date.now();
      const t0 = momento ? centro - (ventana * 60e3) / 2 : centro - ventana * 60e3;
      const t1 = momento ? centro + (ventana * 60e3) / 2 : centro;
      try {
        const h = await api.historial(cfg.series.map((s) => s.v), isoLima(t0), isoLima(t1), 400);
        if (!vivo || !graf.current) return;
        setError(null);
        const texto = css('--txt-2');
        const rejilla = css('--borde');
        const lineas = cfg.lineas ?? [];
        graf.current.setOption({
          animation: false,
          grid: { left: 44, right: 44, top: 34, bottom: 26 },
          legend: { top: 4, left: 8, itemWidth: 14, itemHeight: 3, textStyle: { color: texto, fontSize: 11 } },
          tooltip: { trigger: 'axis', valueFormatter: (v: number) => (v == null ? '—' : v.toFixed(2)) },
          xAxis: { type: 'time', min: t0, max: t1, axisLabel: { color: texto, fontSize: 10, hideOverlap: true },
            axisLine: { lineStyle: { color: rejilla } }, splitLine: { show: false } },
          yAxis: cfg.ejes.map((e, i) => ({
            type: 'value', name: e.nombre, min: e.min, max: e.max, nameTextStyle: { color: texto, fontSize: 10 },
            axisLabel: { color: texto, fontSize: 10 }, splitLine: i === 0 ? { lineStyle: { color: rejilla } } : { show: false },
          })),
          series: cfg.series.map((s, i) => {
            const color = css(s.color ?? '--c-pv');
            const refs = [
              ...lineas.filter((l) => l.eje === s.eje && i === cfg.series.findIndex((x) => x.eje === l.eje))
                .map((l) => ({ yAxis: l.valor, name: l.nombre, lineStyle: { color: css('--aviso'), type: 'dashed', width: 1 } })),
              ...(i === 0 && momento ? [{ xAxis: centro, lineStyle: { color: css('--acento'), width: 1.5, type: 'solid' } }] : []),
            ];
            return {
              name: s.nombre, type: 'line', yAxisIndex: s.eje, showSymbol: false, step: s.paso ? 'end' : undefined,
              lineStyle: { width: s.grueso ? 2 : 1.3, type: s.eje === 1 ? 'dashed' : 'solid', color },
              itemStyle: { color }, connectNulls: false,
              data: (h.series[s.v] ?? []).map(([t, v]) => [Date.parse(t), v]),
              markLine: refs.length ? { symbol: 'none', silent: true, label: { show: false }, data: refs } : undefined,
            };
          }),
        }, true);
      } catch (e) {
        if (vivo) setError(String(e));
      }
    }
    cargar();
    const intervalo = momento ? null : window.setInterval(cargar, 5000);
    return () => { vivo = false; if (intervalo) window.clearInterval(intervalo); };
  }, [equipo, momento, ventana, tema]);

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
