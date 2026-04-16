// src/app/memorias/memorias.component.ts
import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../environments/environment';

interface Memoria { id: string; memory: string; }

@Component({
  selector: 'app-memorias',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="mem-page">
      <h1 class="page-title">Memórias Clínicas</h1>
      <p class="page-sub">Padrões e preferências aprendidos durante o uso do Laudifier.</p>
      <div *ngIf="loading()" class="mem-list">
        <div class="skeleton-row" *ngFor="let i of [1,2,3,4,5]"></div>
      </div>
      <div *ngIf="!loading() && memorias().length === 0" class="empty-state">
        Nenhuma memória registrada ainda.
      </div>
      <div *ngIf="!loading() && memorias().length > 0" class="mem-list">
        <div *ngFor="let m of memorias()" class="mem-card">
          <span class="mem-text">{{ m.memory }}</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .mem-page { padding: 32px 40px; height: 100%; overflow-y: auto; box-sizing: border-box; }
    .page-title { font-family: var(--font-heading); font-size: 24px; font-weight: 700; color: var(--colorNeutralForeground1); margin: 0 0 6px; letter-spacing: -0.02em; }
    .page-sub { font-size: 13px; color: var(--colorNeutralForeground3); margin: 0 0 28px; }
    .mem-list { display: flex; flex-direction: column; gap: 10px; }
    .mem-card { padding: 16px 20px; border: 1px solid var(--colorNeutralStroke2); border-radius: 10px; background: var(--colorNeutralBackground2); }
    .mem-text { font-size: 14px; color: var(--colorNeutralForeground1); line-height: 1.6; }
    .skeleton-row { height: 52px; border-radius: 10px; background: var(--colorNeutralBackground3); animation: shimmer 1.4s infinite; }
    @keyframes shimmer { 0%,100%{opacity:1} 50%{opacity:0.5} }
    .empty-state { padding: 48px; text-align: center; font-size: 14px; color: var(--colorNeutralForeground3); }
  `],
})
export class MemoriasComponent implements OnInit {
  private http = inject(HttpClient);
  memorias = signal<Memoria[]>([]);
  loading  = signal(true);

  ngOnInit() {
    this.http.get<Memoria[]>(`${environment.apiUrl}/memorias`).subscribe({
      next:  m  => { this.memorias.set(m); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }
}
