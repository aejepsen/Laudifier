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
      <h1 class="page-title">📊 Dashboard</h1>

      <div *ngIf="loading()" class="kpi-grid">
        <div class="skeleton-kpi" *ngFor="let i of [1,2,3,4]"></div>
      </div>

      <ng-container *ngIf="!loading() && stats() as s">
        <!-- KPIs -->
        <div class="kpi-grid">
          <div class="kpi-card">
            <span class="kpi-icon">📋</span>
            <div><span class="kpi-val">{{ s.total_laudos }}</span><span class="kpi-lbl">Laudos gerados</span></div>
          </div>
          <div class="kpi-card">
            <span class="kpi-icon">📚</span>
            <div><span class="kpi-val">{{ s.por_rag }}</span><span class="kpi-lbl">Baseados no repositório</span></div>
          </div>
          <div class="kpi-card">
            <span class="kpi-icon">🧠</span>
            <div><span class="kpi-val">{{ s.por_fallback }}</span><span class="kpi-lbl">Gerados pelo Claude</span></div>
          </div>
          <div class="kpi-card">
            <span class="kpi-icon">✅</span>
            <div>
              <span class="kpi-val" [style.color]="s.taxa_aprovacao >= 0.8 ? '#059669' : '#d97706'">
                {{ (s.taxa_aprovacao * 100).toFixed(0) }}%
              </span>
              <span class="kpi-lbl">Taxa de aprovação</span>
            </div>
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
          <span>💡</span>
          <div>
            <strong>Melhore a qualidade</strong>
            <p>Mais da metade dos laudos está sendo gerado sem referência no repositório. Adicione mais laudos de referência na aba <strong>Repositório</strong> para melhorar os resultados.</p>
          </div>
        </div>
      </ng-container>
    </div>
  `,
  styles: [`
    .dash-page { padding: 24px; height: 100%; overflow-y: auto; max-width: 860px; margin: 0 auto; }
    .page-title { font-size: 22px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 24px; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 28px; }
    .kpi-card { display: flex; align-items: center; gap: 14px; padding: 18px; border: 1px solid var(--colorNeutralStroke2); border-radius: 10px; background: var(--colorNeutralBackground2); }
    .kpi-icon { font-size: 28px; }
    .kpi-val  { font-size: 26px; font-weight: 700; color: var(--colorNeutralForeground1); display: block; line-height: 1.2; }
    .kpi-lbl  { font-size: 12px; color: var(--colorNeutralForeground3); display: block; }
    .skeleton-kpi { height: 80px; border-radius: 10px; background: var(--colorNeutralBackground3); animation: shimmer 1.4s infinite; }
    @keyframes shimmer { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .section { margin-bottom: 24px; }
    .section-title { font-size: 16px; font-weight: 600; color: var(--colorNeutralForeground1); margin: 0 0 14px; }
    .esp-list { display: flex; flex-direction: column; gap: 10px; }
    .esp-row  { display: flex; align-items: center; gap: 12px; }
    .esp-name { min-width: 140px; font-size: 13px; color: var(--colorNeutralForeground1); }
    .esp-bar-wrap { flex: 1; background: var(--colorNeutralBackground4); border-radius: 4px; height: 8px; }
    .esp-bar  { height: 100%; background: var(--colorBrandBackground); border-radius: 4px; transition: width 0.5s; }
    .esp-count { min-width: 30px; text-align: right; font-size: 13px; color: var(--colorNeutralForeground3); }
    .tip-box  { display: flex; gap: 14px; padding: 16px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 10px; font-size: 14px; }
    .tip-box > span { font-size: 24px; flex-shrink: 0; }
    .tip-box strong { display: block; margin-bottom: 4px; color: #1e40af; }
    .tip-box p { margin: 0; color: #1e3a8a; font-size: 13px; }
    @media (max-width: 700px) { .kpi-grid { grid-template-columns: 1fr 1fr; } }
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


// ─────────────────────────────────────────────────────────────────────────────
// src/app/laudos/visualizar-laudo.component.ts
// ─────────────────────────────────────────────────────────────────────────────

import { Component, OnInit, signal, inject as inj } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { LaudoService, LaudoSalvo } from '../core/services/laudo.service';
import { VoiceService } from '../core/services/voice.service';
import { marked } from 'marked';

@Component({
  selector: 'app-visualizar-laudo',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="view-page" *ngIf="laudo() as l">
      <div class="view-header">
        <button class="btn-back" (click)="router.navigate(['/historico'])">← Voltar</button>
        <div class="view-info">
          <span class="esp-badge">{{ l.especialidade }}</span>
          <span class="data">{{ l.created_at | date:'dd/MM/yyyy HH:mm' }}</span>
          <span class="geracao-badge" [class]="l.tipo_geracao">
            {{ l.tipo_geracao === 'rag' ? '📚 Repositório' : '🧠 Claude' }}
          </span>
        </div>
        <div class="view-actions">
          <button class="btn-action" (click)="voice.isSpeaking() ? voice.stopSpeaking() : lerLaudo()">
            {{ voice.isSpeaking() ? '⏹ Parar' : '🔊 Ouvir' }}
          </button>
          <button class="btn-action" (click)="editando.set(!editando())">
            {{ editando() ? '👁 Ver' : '✏️ Editar' }}
          </button>
          <button class="btn-action primary" (click)="exportar('pdf')">⬇️ PDF</button>
          <button class="btn-action" (click)="exportar('docx')">⬇️ DOCX</button>
        </div>
      </div>

      <div class="view-body">
        <div *ngIf="!editando()" class="laudo-text markdown-body"
             [innerHTML]="renderMarkdown(l.laudo_editado || l.laudo)"></div>
        <textarea *ngIf="editando()" [(ngModel)]="textoEditado"
                  class="laudo-editor" rows="30" (blur)="salvarEdicao()"></textarea>
      </div>

      <div class="view-footer" *ngIf="!l.aprovado">
        <span>Laudo revisado?</span>
        <button class="btn-feedback ok" (click)="aprovar()">👍 Aprovar</button>
        <button class="btn-feedback nok" (click)="rejeitar()">✏️ Ajustes</button>
      </div>
      <div class="view-footer aprovado" *ngIf="l.aprovado === true">✅ Laudo aprovado pelo médico</div>
    </div>

    <div class="loading" *ngIf="loading()">Carregando laudo...</div>
  `,
  styles: [`
    .view-page { padding: 24px; height: 100%; overflow-y: auto; max-width: 900px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
    .view-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
    .btn-back { background: none; border: 1px solid var(--colorNeutralStroke1); border-radius: 6px; padding: 7px 14px; cursor: pointer; font-size: 14px; color: var(--colorNeutralForeground1); }
    .view-info { display: flex; gap: 10px; align-items: center; flex: 1; flex-wrap: wrap; }
    .esp-badge { font-size: 13px; font-weight: 700; color: var(--colorBrandForeground1); }
    .data { font-size: 12px; color: var(--colorNeutralForeground3); }
    .geracao-badge { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 10px; }
    .geracao-badge.rag { background: #d1fae5; color: #065f46; }
    .geracao-badge.fallback { background: #fef3c7; color: #92400e; }
    .view-actions { display: flex; gap: 8px; }
    .btn-action { padding: 7px 14px; border: 1px solid var(--colorNeutralStroke1); border-radius: 6px; background: transparent; font-size: 13px; cursor: pointer; color: var(--colorNeutralForeground1); }
    .btn-action:hover { background: var(--colorNeutralBackground3); }
    .btn-action.primary { background: var(--colorBrandBackground); color: white; border-color: transparent; }
    .view-body { background: var(--colorNeutralBackground2); border: 1px solid var(--colorNeutralStroke2); border-radius: 10px; padding: 24px; flex: 1; }
    .laudo-text { font-size: 14px; line-height: 1.8; color: var(--colorNeutralForeground1); }
    .markdown-body h1,h2,h3 { font-weight: 700; margin: 14px 0 6px; }
    .markdown-body p { margin: 6px 0; }
    .markdown-body strong { font-weight: 700; }
    .laudo-editor { width: 100%; min-height: 400px; padding: 16px; border: 1px solid var(--colorNeutralStroke1); border-radius: 8px; font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.7; background: var(--colorNeutralBackground1); color: var(--colorNeutralForeground1); resize: vertical; outline: none; box-sizing: border-box; }
    .view-footer { display: flex; align-items: center; gap: 12px; padding: 14px 0; border-top: 1px solid var(--colorNeutralStroke2); font-size: 14px; color: var(--colorNeutralForeground2); }
    .view-footer.aprovado { color: #059669; font-weight: 600; }
    .btn-feedback { padding: 7px 16px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .btn-feedback.ok  { background: #d1fae5; color: #065f46; }
    .btn-feedback.nok { background: #fef3c7; color: #92400e; }
    .loading { padding: 40px; text-align: center; color: var(--colorNeutralForeground3); }
  `],
})
export class VisualizarLaudoComponent implements OnInit {
  private route    = inj(ActivatedRoute);
  private laudoSvc = inj(LaudoService);
  readonly router  = inj(Router);
  readonly voice   = inj(VoiceService);

  laudo        = signal<LaudoSalvo | null>(null);
  loading      = signal(true);
  editando     = signal(false);
  textoEditado = '';

  ngOnInit() {
    const id = this.route.snapshot.paramMap.get('id')!;
    this.laudoSvc.get(id).subscribe({
      next:  l  => { this.laudo.set(l); this.textoEditado = l.laudo_editado || l.laudo; this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  lerLaudo() {
    const l = this.laudo();
    if (l) this.voice.speak(l.laudo_editado || l.laudo, 0.85);
  }

  salvarEdicao() {
    const l = this.laudo();
    if (!l || this.textoEditado === (l.laudo_editado || l.laudo)) return;
    this.laudoSvc.atualizar(l.id, this.textoEditado).subscribe(() => {
      this.laudo.update(cur => cur ? { ...cur, laudo_editado: this.textoEditado } : cur);
    });
  }

  aprovar() {
    const l = this.laudo();
    if (!l) return;
    this.laudoSvc.feedback(l.id, true).subscribe(() =>
      this.laudo.update(c => c ? { ...c, aprovado: true } : c)
    );
  }

  rejeitar() {
    const l = this.laudo();
    if (!l) return;
    const c = prompt('Descreva os ajustes necessários:') ?? undefined;
    this.laudoSvc.feedback(l.id, false, c).subscribe(() =>
      this.laudo.update(cur => cur ? { ...cur, aprovado: false } : cur)
    );
  }

  exportar(fmt: 'pdf' | 'docx') {
    const l = this.laudo();
    if (l) window.open(this.laudoSvc.exportar(l.id, fmt), '_blank');
  }

  renderMarkdown(t: string) { return marked(t) as string; }
}
