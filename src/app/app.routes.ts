// src/app/app.routes.ts
import { Routes } from '@angular/router';
import { AuthGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  { path: 'login',   loadComponent: () => import('./login/login.component').then(m => m.LoginComponent) },
  { path: 'auth/callback', loadComponent: () => import('./login/login.component').then(m => m.LoginComponent) },
  {
    path: '',
    loadComponent: () => import('./shell/shell.component').then(m => m.ShellComponent),
    canActivate: [AuthGuard],
    children: [
      { path: '',          redirectTo: 'gerar', pathMatch: 'full' },
      { path: 'gerar',     loadComponent: () => import('./laudos/gerar-laudo.component').then(m => m.GerarLaudoComponent) },
      { path: 'historico', loadComponent: () => import('./historico/historico.component').then(m => m.HistoricoComponent) },
      { path: 'repositorio', loadComponent: () => import('./repositorio/repositorio.component').then(m => m.RepositorioComponent) },
      { path: 'dashboard', loadComponent: () => import('./dashboard/dashboard.component').then(m => m.DashboardComponent) },
      { path: 'laudo/:id', loadComponent: () => import('./laudos/visualizar-laudo.component').then(m => m.VisualizarLaudoComponent) },
      { path: 'memoria', loadComponent: () => import('./memorias/memorias.component').then(m => m.MemoriasComponent) },
    ],
  },
  { path: '**', redirectTo: 'gerar' },
];


// ─────────────────────────────────────────────────────────────────────────────
// src/app/app.config.ts
// ─────────────────────────────────────────────────────────────────────────────

import { ApplicationConfig } from '@angular/core';
import { provideRouter, withViewTransitions } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes, withViewTransitions()),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimations(),
  ],
};

// authInterceptor inline (importa de core/auth)
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from './core/auth/auth.service';
import { from, switchMap } from 'rxjs';
import { environment } from '../environments/environment';

const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  if (!req.url.includes(environment.apiUrl)) return next(req);
  return from(auth.getToken()).pipe(
    switchMap(token => next(token
      ? req.clone({ headers: req.headers.set('Authorization', `Bearer ${token}`) })
      : req
    ))
  );
};


// ─────────────────────────────────────────────────────────────────────────────
// src/app/core/auth/auth.guard.ts
// ─────────────────────────────────────────────────────────────────────────────

import { inject as _inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService as _AuthService } from './auth.service';

export const AuthGuard: CanActivateFn = () => {
  const auth   = _inject(_AuthService);
  const router = _inject(Router);
  if (auth.isLoggedIn()) return true;
  return router.createUrlTree(['/login']);
};


// ─────────────────────────────────────────────────────────────────────────────
// src/environments/environment.example.ts
// ─────────────────────────────────────────────────────────────────────────────

export const environment = {
  production:   false,
  apiUrl:       'http://localhost:8000',
  supabaseUrl:  'https://seu-projeto.supabase.co',
  supabaseKey:  'sua-anon-key',
  appName:      'Laudifier',
  appVersion:   '1.0.0',
};


// ─────────────────────────────────────────────────────────────────────────────
// src/app/shell/shell.component.ts
// ─────────────────────────────────────────────────────────────────────────────

import { Component, inject, computed as _computed } from '@angular/core';
import { CommonModule as _CM } from '@angular/common';
import { RouterModule, RouterLink as _RL, RouterLinkActive as _RLA } from '@angular/router';
import { AuthService as _AS } from './core/auth/auth.service';

export class ShellComponent {
  /* see shell.component file */
}
