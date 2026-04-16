// src/app/historico/historico.component.ts
import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { LaudoService, LaudoSalvo, ESPECIALIDADES } from '../core/services/laudo.service';

@Component({
  selector: 'app-historico',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="historico-page">
      <div class="page-header">
        <h1>Histórico</h1>
        <p>{{ laudos().length }} laudos gerados</p>
      </div>

      <!-- Filtros -->
      <div class="filters">
        <input class="search-input" [(ngModel)]="busca" placeholder="Buscar por especialidade ou conteúdo..." />
        <select [(ngModel)]="filtroEsp" class="filter-select">
          <option value="">Todas as especialidades</option>
          <option *ngFor="let e of especialidades" [value]="e">{{ e }}</option>
        </select>
      </div>

      <!-- Loading -->
      <div *ngIf="loading()" class="skeleton-list">
        <div class="skeleton-row" *ngFor="let i of [1,2,3,4,5]"></div>
      </div>

      <!-- Empty -->
      <div *ngIf="!loading() && filtered().length === 0" class="empty">
        <svg class="empty-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="8" y="4" width="32" height="40" rx="4" stroke="currentColor" stroke-width="2"/>
          <path d="M16 16h16M16 24h16M16 32h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <p class="empty-title">Nenhum laudo encontrado</p>
        <p class="empty-sub">Gere o primeiro laudo para começar a construir seu histórico.</p>
      </div>

      <!-- Lista -->
      <div class="laudo-list" *ngIf="!loading()">
        <div *ngFor="let laudo of filtered()" class="laudo-row"
             (click)="abrir(laudo.id)">
          <div class="laudo-info">
            <span class="esp-badge">{{ laudo.especialidade }}</span>
            <span class="laudo-preview">{{ getPreview(laudo) }}</span>
          </div>
          <div class="laudo-meta">
            <span class="geracao-badge" [class]="laudo.tipo_geracao">
              {{ laudo.tipo_geracao === 'rag' ? 'RAG' : 'LLM' }}
            </span>
            <span class="status-dot ok"  *ngIf="laudo.aprovado === true"  title="Aprovado"></span>
            <span class="status-dot nok" *ngIf="laudo.aprovado === false" title="Com ajustes"></span>
            <span class="data">{{ laudo.created_at | date:'dd/MM/yy HH:mm' }}</span>
            <div class="row-actions">
              <button class="btn-sm" (click)="exportar($event, laudo.id, 'pdf')">PDF</button>
              <button class="btn-sm" (click)="exportar($event, laudo.id, 'docx')">DOCX</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Paginação -->
      <div class="pagination" *ngIf="hasMore()">
        <button class="btn-mais" (click)="carregarMais()">Carregar mais</button>
      </div>
    </div>
  `,
  styles: [`
    .historico-page { padding: 32px 40px; height: 100%; overflow-y: auto; box-sizing: border-box; }
    .page-header { margin-bottom: 24px; }
    .page-header h1 { font-family: var(--font-heading); font-size: 24px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 4px; letter-spacing: -0.02em; }
    .page-header p  { font-size: 13px; color: var(--colorNeutralForeground3); margin: 0; }
    .filters { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
    .search-input, .filter-select { padding: 9px 14px; border: 1px solid var(--colorNeutralStroke1); border-radius: 8px; font-size: 14px; background: var(--colorNeutralBackground2); color: var(--colorNeutralForeground1); outline: none; transition: border-color 0.15s; }
    .search-input { flex: 1; min-width: 200px; }
    .search-input:focus, .filter-select:focus { border-color: var(--colorBrandStroke1); }
    .skeleton-list { display: flex; flex-direction: column; gap: 8px; }
    .skeleton-row { height: 64px; border-radius: 8px; background: var(--colorNeutralBackground3); animation: shimmer 1.4s infinite; }
    @keyframes shimmer { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .empty { display: flex; flex-direction: column; align-items: center; padding: 80px 24px; color: var(--colorNeutralForeground3); gap: 12px; }
    .empty-icon { width: 48px; height: 48px; opacity: 0.3; }
    .empty-title { font-size: 15px; font-weight: 600; color: var(--colorNeutralForeground2); margin: 0; }
    .empty-sub { font-size: 13px; color: var(--colorNeutralForeground3); margin: 0; text-align: center; max-width: 280px; line-height: 1.5; }
    .laudo-list { display: flex; flex-direction: column; gap: 6px; }
    .laudo-row { display: flex; align-items: center; gap: 16px; padding: 14px 18px; border: 1px solid var(--colorNeutralStroke2); border-radius: 8px; background: var(--colorNeutralBackground2); cursor: pointer; transition: border-color 0.13s, background-color 0.13s; }
    .laudo-row:hover { border-color: var(--colorBrandStroke1); background: var(--colorBrandBackground2); }
    .laudo-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
    .esp-badge { font-size: 12px; font-weight: 700; color: var(--colorBrandForeground1); }
    .laudo-preview { font-size: 13px; color: var(--colorNeutralForeground2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .laudo-meta { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
    .geracao-badge { font-size: 10px; font-weight: 700; letter-spacing: 0.06em; padding: 2px 8px; border-radius: 4px; }
    .geracao-badge.rag      { background: rgba(16,185,129,0.12); color: #10b981; }
    .geracao-badge.fallback { background: rgba(245,158,11,0.12); color: #f59e0b; }
    .status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
    .status-dot.ok  { background: #10b981; }
    .status-dot.nok { background: #f59e0b; }
    .data { font-size: 12px; color: var(--colorNeutralForeground3); }
    .row-actions { display: flex; gap: 4px; }
    .btn-sm { padding: 4px 10px; border: 1px solid var(--colorNeutralStroke1); border-radius: 5px; background: transparent; font-size: 12px; cursor: pointer; color: var(--colorNeutralForeground2); transition: background-color 0.12s; }
    .btn-sm:hover { background: var(--colorNeutralBackground4); }
    .pagination { display: flex; justify-content: center; margin-top: 20px; }
    .btn-mais { padding: 10px 24px; border: 1px solid var(--colorNeutralStroke1); border-radius: 8px; background: transparent; font-size: 14px; cursor: pointer; color: var(--colorNeutralForeground1); transition: background-color 0.12s, border-color 0.12s; }
    .btn-mais:hover { background: var(--colorBrandBackground2); border-color: var(--colorBrandStroke1); }
  `],
})
export class HistoricoComponent implements OnInit {
  private laudoSvc = inject(LaudoService);
  private router   = inject(Router);

  laudos      = signal<LaudoSalvo[]>([]);
  loading     = signal(true);
  hasMore     = signal(false);
  busca       = '';
  filtroEsp   = '';
  page        = 0;
  especialidades = ESPECIALIDADES;

  filtered() {
    let list = this.laudos();
    if (this.busca) {
      const b = this.busca.toLowerCase();
      list = list.filter(l => l.especialidade.toLowerCase().includes(b) || l.solicitacao?.toLowerCase().includes(b));
    }
    if (this.filtroEsp) list = list.filter(l => l.especialidade === this.filtroEsp);
    return list;
  }

  ngOnInit() { this.carregar(); }

  carregar() {
    this.loading.set(true);
    this.laudoSvc.listar(this.page, this.filtroEsp || undefined).subscribe({
      next:  items => { this.laudos.update(l => [...l, ...items]); this.hasMore.set(items.length === 20); this.loading.set(false); },
      error: ()    => this.loading.set(false),
    });
  }

  carregarMais() { this.page++; this.carregar(); }

  abrir(id: string) { this.router.navigate(['/laudo', id]); }

  exportar(event: Event, id: string, fmt: 'pdf' | 'docx') {
    event.stopPropagation();
    window.open(this.laudoSvc.exportar(id, fmt), '_blank');
  }

  getPreview(l: LaudoSalvo) {
    return (l.solicitacao || l.laudo || '').slice(0, 100);
  }
}
