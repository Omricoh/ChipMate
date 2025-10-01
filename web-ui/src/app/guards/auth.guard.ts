import { Injectable } from '@angular/core';
import { CanActivate, Router } from '@angular/router';
import { Observable, map } from 'rxjs';
import { ApiService } from '../services/api.service';

@Injectable({
  providedIn: 'root'
})
export class AuthGuard implements CanActivate {

  constructor(
    private apiService: ApiService,
    private router: Router
  ) {}

  canActivate(): Observable<boolean> | boolean {
    return this.apiService.currentUser$.pipe(
      map(user => {
        if (user && user.is_authenticated) {
          return true;
        } else {
          this.router.navigate(['/login']);
          return false;
        }
      })
    );
  }
}