import { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';

interface D3LineChartProps {
  data: { date: string; value: number }[];
  height?: number;
}

export default function D3LineChart({ data, height = 400 }: D3LineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(600);

  // Handle responsive width
  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setWidth(entry.contentRect.width);
      }
    });

    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  // Render chart
  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const margin = { top: 20, right: 20, bottom: 100, left: 95 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const g = svg
      .attr('width', width)
      .attr('height', height)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Parse dates and prepare data
    const parsedData = data.map((d) => ({
      date: new Date(d.date),
      value: d.value,
      originalDate: d.date,
    }));

    // Scales
    const xScale = d3
      .scaleTime()
      .domain(d3.extent(parsedData, (d) => d.date) as [Date, Date])
      .range([0, innerWidth]);

    const yScale = d3
      .scaleLinear()
      .domain([0, d3.max(parsedData, (d) => d.value) || 0])
      .nice()
      .range([innerHeight, 0]);

    // Grid lines
    g.append('g')
      .attr('class', 'grid')
      .selectAll('line')
      .data(yScale.ticks())
      .join('line')
      .attr('x1', 0)
      .attr('x2', innerWidth)
      .attr('y1', (d) => yScale(d))
      .attr('y2', (d) => yScale(d))
      .attr('class', 'stroke-base-300')
      .attr('stroke-dasharray', '3,3')
      .attr('stroke-width', 1);

    // X-axis
    const tickCount = Math.min(parsedData.length, 10);
    const xAxis = g
      .append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(
        d3
          .axisBottom(xScale)
          .ticks(tickCount)
          .tickFormat((d) => d3.timeFormat('%d %b')(d as Date))
      );

    xAxis
      .selectAll('text')
      .attr('transform', 'rotate(-45)')
      .attr('text-anchor', 'end')
      .attr('dx', '-0.5em')
      .attr('dy', '0.5em')
      .attr('class', 'fill-base-content text-xs');

    xAxis.selectAll('line').attr('class', 'stroke-base-content');
    xAxis.selectAll('path').attr('class', 'stroke-base-content');

    // Y-axis with comma-formatted amounts
    const yAxis = g.append('g').call(
      d3.axisLeft(yScale).tickFormat((d) => `£${d3.format(',')(d as number)}`)
    );

    yAxis.selectAll('text').attr('class', 'fill-base-content text-xs');
    yAxis.selectAll('line').attr('class', 'stroke-base-content');
    yAxis.selectAll('path').attr('class', 'stroke-base-content');

    // Y-axis label (positioned further left to avoid overlap)
    g.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('y', -80)
      .attr('x', -innerHeight / 2)
      .attr('text-anchor', 'middle')
      .attr('class', 'fill-base-content text-sm')
      .text('Daily Spending (£)');

    // Line generator
    const line = d3
      .line<{ date: Date; value: number }>()
      .x((d) => xScale(d.date))
      .y((d) => yScale(d.value))
      .curve(d3.curveMonotoneX);

    // Draw line
    g.append('path')
      .datum(parsedData)
      .attr('class', 'stroke-primary')
      .attr('fill', 'none')
      .attr('stroke-width', 2)
      .attr('d', line);

    // Draw dots
    g.selectAll('.dot')
      .data(parsedData)
      .join('circle')
      .attr('class', 'dot fill-primary')
      .attr('cx', (d) => xScale(d.date))
      .attr('cy', (d) => yScale(d.value))
      .attr('r', 4);

    // Tooltip
    const tooltip = d3
      .select(containerRef.current)
      .append('div')
      .attr('class', 'absolute hidden bg-base-200 px-2 py-1 rounded text-sm shadow-lg pointer-events-none z-50')
      .style('position', 'absolute');

    g.selectAll('.dot')
      .on('mouseover', function (event, d: { date: Date; value: number; originalDate: string }) {
        tooltip
          .html(`<strong>${d.originalDate}</strong><br/>£${d.value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
          .classed('hidden', false);
        d3.select(this).attr('r', 6);
      })
      .on('mousemove', function (event) {
        const [x, y] = d3.pointer(event, containerRef.current);
        tooltip.style('left', `${x + 10}px`).style('top', `${y - 10}px`);
      })
      .on('mouseout', function () {
        tooltip.classed('hidden', true);
        d3.select(this).attr('r', 4);
      });

    return () => {
      tooltip.remove();
    };
  }, [data, width, height]);

  if (data.length === 0) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <svg ref={svgRef} />
    </div>
  );
}
