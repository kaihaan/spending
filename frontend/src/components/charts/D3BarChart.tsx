import { useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';

interface D3BarChartProps {
  data: Array<{ label: string; value: number }>;
  height?: number;
  onBarClick?: (label: string) => void;
}

export default function D3BarChart({ data, height = 400, onBarClick }: D3BarChartProps) {
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

    // Scales
    const xScale = d3
      .scaleBand()
      .domain(data.map((d) => d.label))
      .range([0, innerWidth])
      .padding(0.2);

    const yScale = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.value) || 0])
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
    const xAxis = g
      .append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(d3.axisBottom(xScale));

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
      .text('Amount (£)');

    // Bars
    g.selectAll('.bar')
      .data(data)
      .join('rect')
      .attr('class', 'bar fill-primary')
      .attr('x', (d) => xScale(d.label) || 0)
      .attr('y', (d) => yScale(d.value))
      .attr('width', xScale.bandwidth())
      .attr('height', (d) => innerHeight - yScale(d.value))
      .attr('rx', 2)
      .style('cursor', onBarClick ? 'pointer' : 'default');

    // Tooltip
    const tooltip = d3
      .select(containerRef.current)
      .append('div')
      .attr('class', 'absolute hidden bg-base-200 px-2 py-1 rounded text-sm shadow-lg pointer-events-none z-50')
      .style('position', 'absolute');

    g.selectAll('.bar')
      .on('mouseover', function (event, d: { label: string; value: number }) {
        tooltip
          .html(`<strong>${d.label}</strong><br/>£${d.value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)
          .classed('hidden', false);
        d3.select(this).attr('opacity', 0.8);
      })
      .on('mousemove', function (event) {
        const [x, y] = d3.pointer(event, containerRef.current);
        tooltip.style('left', `${x + 10}px`).style('top', `${y - 10}px`);
      })
      .on('mouseout', function () {
        tooltip.classed('hidden', true);
        d3.select(this).attr('opacity', 1);
      })
      .on('click', function (event, d: { label: string; value: number }) {
        if (onBarClick) {
          onBarClick(d.label);
        }
      });

    return () => {
      tooltip.remove();
    };
  }, [data, width, height, onBarClick]);

  if (data.length === 0) {
    return null;
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <svg ref={svgRef} />
    </div>
  );
}
