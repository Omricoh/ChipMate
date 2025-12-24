import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../services/api.service';
import { User } from '../../models/user.model';
import { Observable, take } from 'rxjs';

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [CommonModule, RouterModule, FormsModule],
  template: `
    <div class="container mt-5">
      <!-- Hero Section -->
      <div class="row justify-content-center mb-5">
        <div class="col-lg-8 text-center">
          <div class="card game-card bg-light-custom">
            <div class="card-body p-5">
              <h1 class="display-4 text-primary-custom mb-4">
                <i class="bi bi-suit-spade-fill me-3"></i>
                Welcome to ChipMate
              </h1>
              <p class="lead mb-4">
                The ultimate poker game management tool. Track buy-ins, cashouts, and debts with ease.
              </p>

              <div class="row g-4 mt-4" *ngIf="!(currentUser$ | async)">
                <div class="col-md-6">
                  <a routerLink="/login" class="btn btn-primary btn-lg w-100">
                    <i class="bi bi-person-plus me-2"></i>
                    Get Started
                  </a>
                </div>
                <div class="col-md-6">
                  <button class="btn btn-outline-primary btn-lg w-100" (click)="showJoinDialog = true">
                    <i class="bi bi-box-arrow-in-right me-2"></i>
                    Join Game
                  </button>
                </div>
              </div>

              <div class="row g-4 mt-4" *ngIf="currentUser$ | async as user">
                <!-- Admin user sees only admin dashboard button -->
                <div class="col-12" *ngIf="user.is_admin">
                  <a routerLink="/admin" class="btn btn-warning btn-lg w-100">
                    <i class="bi bi-shield-check me-2"></i>
                    Admin Dashboard
                  </a>
                </div>

                <!-- Regular users see game options -->
                <ng-container *ngIf="!user.is_admin">
                  <div class="col-md-6">
                    <a routerLink="/create-game" class="btn btn-success btn-lg w-100">
                      <i class="bi bi-plus-circle me-2"></i>
                      Create New Game
                    </a>
                  </div>
                  <div class="col-md-6" *ngIf="user.current_game_id">
                    <a [routerLink]="['/game', user.current_game_id]" class="btn btn-primary btn-lg w-100">
                      <i class="bi bi-play-circle me-2"></i>
                      Continue Game
                    </a>
                  </div>
                  <div class="col-md-6" *ngIf="!user.current_game_id">
                    <button class="btn btn-outline-primary btn-lg w-100" (click)="showJoinDialog = true">
                      <i class="bi bi-box-arrow-in-right me-2"></i>
                      Join Game
                    </button>
                  </div>
                </ng-container>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Features Section -->
      <div class="row g-4 mb-5">
        <div class="col-md-4">
          <div class="card game-card h-100">
            <div class="card-body text-center p-4">
              <div class="mb-3">
                <i class="bi bi-cash-stack text-success" style="font-size: 3rem;"></i>
              </div>
              <h5 class="card-title">Track Buy-ins</h5>
              <p class="card-text">
                Easily track cash and credit buy-ins for all players. Keep accurate records of all transactions.
              </p>
            </div>
          </div>
        </div>

        <div class="col-md-4">
          <div class="card game-card h-100">
            <div class="card-body text-center p-4">
              <div class="mb-3">
                <i class="bi bi-arrow-up-right-circle text-warning" style="font-size: 3rem;"></i>
              </div>
              <h5 class="card-title">Manage Cashouts</h5>
              <p class="card-text">
                Process cashouts with automatic debt settlement and transfers. Handle complex debt scenarios easily.
              </p>
            </div>
          </div>
        </div>

        <div class="col-md-4">
          <div class="card game-card h-100">
            <div class="card-body text-center p-4">
              <div class="mb-3">
                <i class="bi bi-qr-code text-info" style="font-size: 3rem;"></i>
              </div>
              <h5 class="card-title">QR Code Joining</h5>
              <p class="card-text">
                Generate QR codes for easy game joining. Players can scan and join instantly without manual codes.
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- How It Works Section -->
      <div class="row justify-content-center">
        <div class="col-lg-10">
          <div class="card game-card">
            <div class="card-header">
              <h3 class="mb-0">
                <i class="bi bi-lightbulb me-2"></i>
                How It Works
              </h3>
            </div>
            <div class="card-body">
              <div class="row g-4">
                <div class="col-md-3 text-center">
                  <div class="mb-3">
                    <span class="badge bg-primary rounded-circle p-3" style="font-size: 1.5rem;">1</span>
                  </div>
                  <h6>Create Game</h6>
                  <small class="text-muted">Host creates a new poker game and gets a unique game code</small>
                </div>
                <div class="col-md-3 text-center">
                  <div class="mb-3">
                    <span class="badge bg-primary rounded-circle p-3" style="font-size: 1.5rem;">2</span>
                  </div>
                  <h6>Players Join</h6>
                  <small class="text-muted">Players join using the game code or by scanning the QR code</small>
                </div>
                <div class="col-md-3 text-center">
                  <div class="mb-3">
                    <span class="badge bg-primary rounded-circle p-3" style="font-size: 1.5rem;">3</span>
                  </div>
                  <h6>Track Transactions</h6>
                  <small class="text-muted">Record buy-ins and cashouts with automatic debt management</small>
                </div>
                <div class="col-md-3 text-center">
                  <div class="mb-3">
                    <span class="badge bg-primary rounded-circle p-3" style="font-size: 1.5rem;">4</span>
                  </div>
                  <h6>Final Settlement</h6>
                  <small class="text-muted">Get complete settlement data with all debts and payments</small>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Join Game Dialog -->
    <div class="modal fade" [class.show]="showJoinDialog" [style.display]="showJoinDialog ? 'block' : 'none'" tabindex="-1">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="bi bi-box-arrow-in-right me-2"></i>
              Join Game
            </h5>
            <button type="button" class="btn-close" (click)="showJoinDialog = false"></button>
          </div>
          <div class="modal-body">
            <p>Enter a game code to join an existing poker game:</p>
            <div class="input-group">
              <input
                type="text"
                class="form-control"
                placeholder="Enter game code (e.g., ABC123)"
                [(ngModel)]="gameCodeInput"
                (keyup.enter)="joinGameByCode()"
                #gameCodeInput
              >
              <button class="btn btn-primary" (click)="joinGameByCode()" [disabled]="!gameCodeInput">
                Join
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="modal-backdrop fade" [class.show]="showJoinDialog" *ngIf="showJoinDialog" (click)="showJoinDialog = false"></div>
  `,
  styles: [`
    .modal {
      background-color: rgba(0,0,0,0.5);
    }
  `]
})
export class HomeComponent implements OnInit {
  currentUser$: Observable<User | null>;
  showJoinDialog = false;
  gameCodeInput = '';

  constructor(
    private apiService: ApiService,
    private router: Router
  ) {
    this.currentUser$ = this.apiService.currentUser$;
  }

  ngOnInit(): void {
    // Redirect admin users to admin dashboard
    const currentUser = this.apiService.getCurrentUser();
    if (currentUser && currentUser.is_admin) {
      this.router.navigate(['/admin']);
    }
  }

  joinGameByCode(): void {
    if (this.gameCodeInput.trim()) {
      // Navigate to join page with game code
      window.location.href = `/join/${this.gameCodeInput.trim().toUpperCase()}`;
    }
  }
}