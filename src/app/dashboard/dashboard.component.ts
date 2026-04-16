// src/app/dashboard/dashboard.component.ts
import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LaudoService } from '../core/services/laudo.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="dash-page">
      <h1 class="page-title">Dashboard</h1>

      <div *ngIf="loading()" class="kpi-grid">
        <div class="skeleton-kpi" *ngFor="let i of [1,2,3,4]"></div>
      </div>

      <ng-container *ngIf="!loading() && stats() as s">
        <!-- KPIs -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <span class="kpi-accent">Laudos</span>
            <span class="kpi-val">{{ s.total_laudos }}</span>
            <span class="kpi-lbl">Gerados</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-accent">RAG</span>
            <span class="kpi-val">{{ s.por_rag }}</span>
            <span class="kpi-lbl">Do repositório</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-accent">LLM</span>
            <span class="kpi-val">{{ s.por_fallback }}</span>
            <span class="kpi-lbl">Pelo Claude</span>
          </div>
          <div class="kpi-card">
            <span class="kpi-accent">Taxa</span>
            <span class="kpi-val" [class.kpi-val--good]="s.taxa_aprovacao >= 0.8" [class.kpi-val--warn]="s.taxa_aprovacao < 0.8">
              {{ (s.taxa_aprovacao * 100).toFixed(0) }}%
            </span>
            <span class="kpi-lbl">Aprovação</span>
          </div>
        </div>

        <!-- Por especialidade -->
        <div class="section" *ngIf="s.por_especialidade">
          <h2 class="section-title">Por Especialidade</h2>
          <div class="esp-list">
            <div *ngFor="let item of espItems(s.por_especialidade)" class="esp-row">
              <span class="esp-name">{{ item.esp }}</span>
              <div class="esp-bar-wrap">
                <div class="esp-bar" [style.width.%]="item.pct"></div>
              </div>
              <span class="esp-count">{{ item.count }}</span>
            </div>
          </div>
        </div>

        <!-- Dicas -->
        <div class="tip-box" *ngIf="s.por_rag < s.total_laudos * 0.5">
          <div class="tip-dot"></div>
          <div>
            <strong>Melhore a qualidade</strong>
            <p>Mais da metade dos laudos está sendo gerado sem referência no repositório. Adicione laudos de referência na aba <strong>Repositório</strong>.</p>
          </div>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .dash-page { padding: 32px 40px; height: 100%; overflow-y: auto; box-sizing: border-box; }
    .page-title { font-family: var(--font-heading); font-size: 24px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 28px; letter-spacing: -0.02em; }
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 32px; }
    .kpi-card { padding: 20px; border: 1px solid var(--colorNeutralStroke2); border-radius: 12px; background: var(--colorNeutralBackground2); display: flex; flex-direction: column; gap: 4px; }
    .kpi-accent { font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--colorBrandForeground1); }
    .kpi-val  { font-size: 32px; font-weight: 700; color: var(--colorNeutralForeground1); line-height: 1.1; }
    .kpi-val--good { color: #059669; }
    .kpi-val--warn { color: #d97706; }
    .kpi-lbl  { font-size: 12px; color: var(--colorNeutralForeground3); }
    .skeleton-kpi { height: 96px; border-radius: 12px; background: var(--colorNeutralBackground3); animation: shimmer 1.4s infinite; }
    @keyframes shimmer { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .section { margin-bottom: 28px; }
    .section-title { font-size: 14px; font-weight: 600; color: var(--colorNeutralForeground2); margin: 0 0 16px; letter-spacing: 0.02em; text-transform: uppercase; }
    .esp-list { display: flex; flex-direction: column; gap: 12px; }
    .esp-row  { display: flex; align-items: center; gap: 12px; }
    .esp-name { min-width: 140px; font-size: 13px; color: var(--colorNeutralForeground1); }
    .esp-bar-wrap { flex: 1; background: var(--colorNeutralBackground4); border-radius: 4px; height: 6px; }
    .esp-bar  { height: 100%; background: var(--colorBrandForeground1); border-radius: 4px; transition: width 0.6s cubic-bezier(0.4,0,0.2,1); opacity: 0.7; }
    .esp-count { min-width: 30px; text-align: right; font-size: 13px; color: var(--colorNeutralForeground3); }
    .tip-box  { display: flex; gap: 14px; align-items: flex-start; padding: 16px; background: rgba(59,130,246,0.06); border: 1px solid rgba(59,130,246,0.2); border-radius: 10px; font-size: 14px; }
    .tip-dot  { width: 8px; height: 8px; border-radius: 50%; background: var(--colorBrandForeground1); flex-shrink: 0; margin-top: 5px; }
    .tip-box strong { display: block; margin-bottom: 4px; color: var(--colorBrandForeground1); font-size: 13px; }
    .tip-box p { margin: 0; color: var(--colorNeutralForeground2); font-size: 13px; line-height: 1.5; }
  `],
})
export class DashboardComponent implements OnInit {
  private laudoSvc = inject(LaudoService);
  stats   = signal<any>(null);
  loading = signal(true);

  ngOnInit() {
    this.laudoSvc.getDashboardStats().subscribe({
      next:  s  => { this.stats.set(s); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  espItems(obj: Record<string, number>) {
    const total = Object.values(obj).reduce((a, b) => a + b, 0);
    return Object.entries(obj)
      .sort(([,a],[,b]) => b - a)
      .map(([esp, count]) => ({ esp, count, pct: total ? (count / total) * 100 : 0 }));
  }
}

