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
          <span class="brand-icon">🏥</span>
          <div>
            <span class="brand-name">Laudifier</span>
            <span class="brand-sub">Gerador de Laudos</span>
          </div>
        </div>

        <ul class="nav-list">
          <li *ngFor="let item of navItems">
            <a [routerLink]="item.path" routerLinkActive="active" class="nav-item">
              <span class="nav-icon">{{ item.icon }}</span>
              <span class="nav-label">{{ item.label }}</span>
            </a>
          </li>
        </ul>

        <div class="user-info" *ngIf="auth.profile() as p">
          <div class="user-avatar">{{ initials() }}</div>
          <div class="user-details">
            <span class="user-name">{{ p.displayName }}</span>
            <span class="user-crm" *ngIf="p.crm">CRM {{ p.crm }}</span>
          </div>
          <button class="btn-logout" (click)="auth.signOut()" title="Sair">⇥</button>
        </div>
      </nav>

      <main class="main-content">
        <router-outlet />
      </main>
    </div>
  `,
  styles: [`
    .shell { display: flex; height: 100vh; overflow: hidden; }

    .sidebar { width: 220px; display: flex; flex-direction: column; background: #0f2d5e; flex-shrink: 0; }
    .brand   { display: flex; align-items: center; gap: 12px; padding: 20px 16px; border-bottom: 1px solid rgba(255,255,255,0.1); }
    .brand-icon { font-size: 28px; }
    .brand-name { font-size: 16px; font-weight: 700; color: white; display: block; }
    .brand-sub  { font-size: 11px; color: rgba(255,255,255,0.5); }

    .nav-list { list-style: none; padding: 10px 8px; margin: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; }
    .nav-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; text-decoration: none; color: rgba(255,255,255,0.7); font-size: 14px; transition: all 0.12s; }
    .nav-item:hover { background: rgba(255,255,255,0.1); color: white; }
    .nav-item.active { background: rgba(255,255,255,0.15); color: white; font-weight: 600; }
    .nav-icon { font-size: 18px; width: 22px; text-align: center; }

    .user-info { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.1); }
    .user-avatar { width: 32px; height: 32px; border-radius: 50%; background: #1a56db; color: white; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; flex-shrink: 0; }
    .user-details { flex: 1; min-width: 0; }
    .user-name { font-size: 12px; font-weight: 600; color: white; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .user-crm  { font-size: 10px; color: rgba(255,255,255,0.5); }
    .btn-logout { background: none; border: none; cursor: pointer; font-size: 18px; color: rgba(255,255,255,0.5); padding: 4px; border-radius: 4px; }
    .btn-logout:hover { color: white; }

    .main-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; background: var(--colorNeutralBackground1); }
  `],
})
export class ShellComponent {
  readonly auth = inject(AuthService);
  initials = computed(() => {
    const n = this.auth.profile()?.displayName ?? 'M';
    return n.split(' ').map((p: string) => p[0]).slice(0, 2).join('').toUpperCase();
  });
  navItems = [
    { path: '/gerar',       icon: '✨', label: 'Gerar Laudo' },
    { path: '/historico',   icon: '📋', label: 'Histórico' },
    { path: '/repositorio', icon: '📚', label: 'Repositório' },
    { path: '/dashboard',   icon: '📊', label: 'Dashboard' },
  ];
}
