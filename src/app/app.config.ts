// src/app/app.config.ts
import { ApplicationConfig } from '@angular/core';
import { provideRouter, withViewTransitions } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { from, switchMap } from 'rxjs';
import { routes } from './app.routes';
import { AuthService } from './core/auth/auth.service';
import { environment } from '../environments/environment';

const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  if (!req.url.includes(environment.apiUrl)) return next(req);
  return from(auth.getToken()).pipe(
    switchMap(token => next(
      token ? req.clone({ headers: req.headers.set('Authorization', `Bearer ${token}`) }) : req
    ))
  );
};

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes, withViewTransitions()),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimations(),
  ],
};
