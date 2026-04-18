// src/app/shell/shell.component.ts
import { Component, inject, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../core/auth/auth.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, RouterModule, RouterLink, RouterLinkActive],
  template: `
    <div class="shell">
      <nav class="sidebar">
        <div class="brand">
          <svg class="brand-mark" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="32" height="32" rx="8" fill="rgba(255,255,255,0.12)"/>
            <path d="M16 9v14M9 16h14" stroke="white" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
          <div>
            <span class="brand-name">Laudifier</span>
            <span class="brand-sub">Laudos com IA</span>
          </div>
        </div>

        <ul class="nav-list">
          <li>
            <a routerLink="/gerar" routerLinkActive="active" class="nav-item">
              <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>
              </svg>
              <span class="nav-label">Gerar Laudo</span>
            </a>
          </li>
          <li>
            <a routerLink="/historico" routerLinkActive="active" class="nav-item">
              <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              <span class="nav-label">Histórico</span>
            </a>
          </li>
          <li>
            <a routerLink="/repositorio" routerLinkActive="active" class="nav-item">
              <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
              </svg>
              <span class="nav-label">Repositório</span>
            </a>
          </li>
          <li>
            <a routerLink="/dashboard" routerLinkActive="active" class="nav-item">
              <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
                <rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>
              </svg>
              <span class="nav-label">Dashboard</span>
            </a>
          </li>
        </ul>

        <div class="user-info" *ngIf="auth.profile() as p">
          <div class="user-avatar">{{ initials() }}</div>
          <div class="user-details">
            <span class="user-name">{{ p.displayName }}</span>
            <span class="user-crm" *ngIf="p.crm">CRM {{ p.crm }}</span>
          </div>
          <button class="btn-logout" (click)="auth.signOut()" title="Sair">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </nav>

      <main class="main-content">
        <router-outlet />
      </main>
    </div>
  `,
  styles: [`
    .shell { display: flex; height: 100vh; overflow: hidden; }

    .sidebar {
      width: 220px; display: flex; flex-direction: column;
      background: #0a1628; flex-shrink: 0;
      border-right: 1px solid rgba(255,255,255,0.06);
    }
    .brand   { display: flex; align-items: center; gap: 12px; padding: 20px 16px; border-bottom: 1px solid rgba(255,255,255,0.07); }
    .brand-mark { width: 32px; height: 32px; flex-shrink: 0; }
    .brand-name { font-family: var(--font-heading); font-size: 15px; font-weight: 700; color: white; display: block; letter-spacing: -0.02em; }
    .brand-sub  { font-size: 10px; color: rgba(255,255,255,0.35); letter-spacing: 0.02em; text-transform: uppercase; }

    .nav-list { list-style: none; padding: 10px 8px; margin: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
    .nav-item {
      display: flex; align-items: center; gap: 10px; padding: 9px 12px;
      border-radius: 8px; text-decoration: none; color: rgba(255,255,255,0.55);
      font-size: 13.5px; transition: background-color 0.12s, color 0.12s;
    }
    .nav-item:hover { background: rgba(255,255,255,0.07); color: rgba(255,255,255,0.9); }
    .nav-item.active { background: rgba(255,255,255,0.1); color: white; font-weight: 600; }
    .nav-icon { width: 18px; height: 18px; flex-shrink: 0; }

    .user-info { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.07); }
    .user-avatar { width: 30px; height: 30px; border-radius: 50%; background: rgba(96,165,250,0.2); border: 1px solid rgba(96,165,250,0.3); color: #93c5fd; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
    .user-details { flex: 1; min-width: 0; }
    .user-name { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.9); display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .user-crm  { font-size: 10px; color: rgba(255,255,255,0.35); }
    .btn-logout { background: none; border: none; cursor: pointer; color: rgba(255,255,255,0.35); padding: 4px; border-radius: 4px; display: flex; align-items: center; transition: color 0.12s; }
    .btn-logout:hover { color: rgba(255,255,255,0.8); }

    .main-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; background: var(--colorNeutralBackground1); }

    @media (max-width: 768px) {
      .sidebar { width: 56px; }
      .brand-name, .brand-sub, .nav-label, .user-details, .user-crm { display: none; }
      .brand { padding: 16px 12px; justify-content: center; }
      .nav-item { padding: 10px; justify-content: center; }
      .user-info { padding: 12px; justify-content: center; }
      .btn-logout { display: none; }
    }
  `],
})
export class ShellComponent {
  readonly auth = inject(AuthService);
  initials = computed(() => {
    const n = this.auth.profile()?.displayName ?? 'M';
    return n.split(' ').map((p: string) => p[0]).slice(0, 2).join('').toUpperCase();
  });
}
