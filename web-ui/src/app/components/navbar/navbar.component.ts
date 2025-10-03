import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { User } from '../../models/user.model';
import { Observable } from 'rxjs';

@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <nav class="navbar navbar-expand-lg navbar-dark">
      <div class="container">
        <a class="navbar-brand" routerLink="/home">
          <i class="bi bi-suit-spade-fill me-2"></i>
          ChipMate
        </a>

        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
          <span class="navbar-toggler-icon"></span>
        </button>

        <div class="collapse navbar-collapse" id="navbarNav">
          <ul class="navbar-nav me-auto">
            <li class="nav-item">
              <a class="nav-link" routerLink="/home" routerLinkActive="active">
                <i class="bi bi-house me-1"></i>
                Home
              </a>
            </li>
            <li class="nav-item" *ngIf="currentUser$ | async">
              <a class="nav-link" routerLink="/create-game" routerLinkActive="active">
                <i class="bi bi-plus-circle me-1"></i>
                Create Game
              </a>
            </li>
          </ul>

          <ul class="navbar-nav">
            <li class="nav-item" *ngIf="!(currentUser$ | async)">
              <a class="nav-link" routerLink="/login">
                <i class="bi bi-box-arrow-in-right me-1"></i>
                Login
              </a>
            </li>
            <li class="nav-item dropdown" *ngIf="currentUser$ | async as user">
              <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                <i class="bi bi-person-circle me-1"></i>
                {{ user.name }}
              </a>
              <ul class="dropdown-menu">
                <li *ngIf="user.current_game_id">
                  <a class="dropdown-item" [routerLink]="['/game', user.current_game_id]">
                    <i class="bi bi-play-circle me-2"></i>
                    Current Game
                  </a>
                </li>
                <li><hr class="dropdown-divider"></li>
                <li>
                  <a class="dropdown-item" href="#" (click)="logout(); $event.preventDefault()">
                    <i class="bi bi-box-arrow-right me-2"></i>
                    Logout
                  </a>
                </li>
              </ul>
            </li>
          </ul>
        </div>
      </div>
    </nav>
  `,
  styles: []
})
export class NavbarComponent {
  currentUser$: Observable<User | null>;

  constructor(
    private apiService: ApiService,
    private router: Router
  ) {
    this.currentUser$ = this.apiService.currentUser$;
  }

  logout(): void {
    this.apiService.logout();
    this.router.navigate(['/home']);
  }
}