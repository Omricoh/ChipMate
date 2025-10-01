import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../../services/api.service';
import { User } from '../../../models/user.model';

@Component({
  selector: 'app-join-game',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  template: `
    <div class="container mt-5">
      <div class="row justify-content-center">
        <div class="col-md-8 col-lg-6">
          <div class="card game-card">
            <div class="card-header text-center">
              <h4 class="mb-0">
                <i class="bi bi-box-arrow-in-right me-2"></i>
                Join Game
              </h4>
            </div>
            <div class="card-body">
              <div class="alert alert-info text-center" *ngIf="gameCode">
                <i class="bi bi-qr-code me-2"></i>
                Game Code: <strong>{{ gameCode }}</strong>
              </div>

              <form [formGroup]="joinGameForm" (ngSubmit)="onSubmit()">
                <div class="mb-3">
                  <label for="gameCode" class="form-label">Game Code</label>
                  <input
                    type="text"
                    class="form-control text-uppercase"
                    id="gameCode"
                    formControlName="gameCode"
                    placeholder="Enter game code (e.g., ABC123)"
                    [class.is-invalid]="joinGameForm.get('gameCode')?.invalid && joinGameForm.get('gameCode')?.touched"
                    style="letter-spacing: 2px; font-weight: bold;"
                  >
                  <div class="invalid-feedback" *ngIf="joinGameForm.get('gameCode')?.invalid && joinGameForm.get('gameCode')?.touched">
                    Game code is required
                  </div>
                </div>

                <div class="mb-4">
                  <label for="playerName" class="form-label">Your Name</label>
                  <input
                    type="text"
                    class="form-control"
                    id="playerName"
                    formControlName="playerName"
                    placeholder="Enter your name"
                    [class.is-invalid]="joinGameForm.get('playerName')?.invalid && joinGameForm.get('playerName')?.touched"
                  >
                  <div class="invalid-feedback" *ngIf="joinGameForm.get('playerName')?.invalid && joinGameForm.get('playerName')?.touched">
                    Player name is required (minimum 2 characters)
                  </div>
                </div>

                <div class="d-grid">
                  <button
                    type="submit"
                    class="btn btn-primary btn-lg"
                    [disabled]="joinGameForm.invalid || isLoading"
                  >
                    <span *ngIf="isLoading" class="loading-spinner me-2"></span>
                    <i *ngIf="!isLoading" class="bi bi-box-arrow-in-right me-2"></i>
                    {{ isLoading ? 'Joining Game...' : 'Join Game' }}
                  </button>
                </div>
              </form>

              <div class="alert alert-success mt-3" *ngIf="successMessage">
                <i class="bi bi-check-circle me-2"></i>
                {{ successMessage }}
              </div>

              <div class="alert alert-danger mt-3" *ngIf="errorMessage">
                <i class="bi bi-exclamation-triangle me-2"></i>
                {{ errorMessage }}
              </div>

              <div class="mt-4 text-center">
                <a routerLink="/home" class="btn btn-outline-secondary">
                  <i class="bi bi-arrow-left me-2"></i>
                  Back to Home
                </a>
              </div>

              <div class="mt-4">
                <div class="alert alert-light">
                  <i class="bi bi-info-circle me-2"></i>
                  <strong>Need help?</strong>
                  <ul class="mb-0 mt-2">
                    <li>Ask the host for the game code</li>
                    <li>Game codes are usually 5-6 characters (e.g., ABC123)</li>
                    <li>You can also scan a QR code if the host provides one</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: []
})
export class JoinGameComponent implements OnInit {
  joinGameForm: FormGroup;
  isLoading = false;
  errorMessage = '';
  successMessage = '';
  gameCode = '';

  constructor(
    private formBuilder: FormBuilder,
    private apiService: ApiService,
    private router: Router,
    private route: ActivatedRoute
  ) {
    this.joinGameForm = this.formBuilder.group({
      gameCode: ['', [Validators.required]],
      playerName: ['', [Validators.required, Validators.minLength(2)]]
    });

    // Pre-fill with current user's name if available
    const currentUser = this.apiService.getCurrentUser();
    if (currentUser) {
      this.joinGameForm.patchValue({
        playerName: currentUser.name
      });
    }
  }

  ngOnInit(): void {
    // Get game code from route params if available
    this.route.params.subscribe(params => {
      if (params['gameCode']) {
        this.gameCode = params['gameCode'].toUpperCase();
        this.joinGameForm.patchValue({
          gameCode: this.gameCode
        });
      }
    });

    // Convert game code to uppercase as user types
    this.joinGameForm.get('gameCode')?.valueChanges.subscribe(value => {
      if (value) {
        const upperValue = value.toUpperCase();
        if (upperValue !== value) {
          this.joinGameForm.get('gameCode')?.setValue(upperValue, { emitEvent: false });
        }
      }
    });
  }

  onSubmit(): void {
    if (this.joinGameForm.valid) {
      this.isLoading = true;
      this.errorMessage = '';
      this.successMessage = '';

      const gameCode = this.joinGameForm.value.gameCode.trim().toUpperCase();
      const playerName = this.joinGameForm.value.playerName.trim();

      this.apiService.joinGame(gameCode, playerName).subscribe({
        next: (response) => {
          this.isLoading = false;
          this.successMessage = response.message;

          // Create or update user
          const currentUser = this.apiService.getCurrentUser();
          const user: User = {
            id: currentUser?.id || Date.now(), // Generate ID if needed
            name: playerName,
            is_authenticated: true,
            current_game_id: response.game_id,
            is_host: false
          };

          this.apiService.setCurrentUser(user);

          // Navigate to the game after a short delay
          setTimeout(() => {
            this.router.navigate(['/game', response.game_id]);
          }, 2000);
        },
        error: (error) => {
          this.isLoading = false;
          this.errorMessage = error.error?.message || 'Failed to join game. Please check the game code and try again.';
        }
      });
    }
  }
}