// src/app/app.routes.ts
import { Routes } from '@angular/router';
import { AuthGuard } from './core/auth/auth.guard';
import { AdminGuard } from './core/auth/admin.guard';

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
      { path: 'repositorio', canActivate: [AdminGuard], loadComponent: () => import('./repositorio/repositorio.component').then(m => m.RepositorioComponent) },
      { path: 'dashboard',  canActivate: [AdminGuard], loadComponent: () => import('./dashboard/dashboard.component').then(m => m.DashboardComponent) },
      { path: 'laudo/:id', loadComponent: () => import('./laudos/visualizar-laudo.component').then(m => m.VisualizarLaudoComponent) },
      { path: 'memoria', loadComponent: () => import('./memorias/memorias.component').then(m => m.MemoriasComponent) },
    ],
  },
  { path: '**', redirectTo: 'gerar' },
];
