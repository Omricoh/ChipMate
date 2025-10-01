import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../../services/api.service';
import { AuthRequest } from '../../../models/user.model';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  template: `
    <div class="container mt-5">
      <div class="row justify-content-center">
        <div class="col-md-6 col-lg-4">
          <div class="card game-card">
            <div class="card-header text-center">
              <h4 class="mb-0">
                <i class="bi bi-person-circle me-2"></i>
                Welcome to ChipMate
              </h4>
            </div>
            <div class="card-body">
              <form [formGroup]="loginForm" (ngSubmit)="onSubmit()">
                <div class="mb-3">
                  <label for="name" class="form-label">Your Name</label>
                  <input
                    type="text"
                    class="form-control"
                    id="name"
                    formControlName="name"
                    placeholder="Enter your name"
                    [class.is-invalid]="loginForm.get('name')?.invalid && loginForm.get('name')?.touched"
                  >
                  <div class="invalid-feedback" *ngIf="loginForm.get('name')?.invalid && loginForm.get('name')?.touched">
                    Name is required
                  </div>
                </div>

                <div class="mb-3">
                  <label for="userId" class="form-label">User ID (Optional)</label>
                  <input
                    type="number"
                    class="form-control"
                    id="userId"
                    formControlName="user_id"
                    placeholder="Leave empty for new user"
                  >
                  <small class="form-text text-muted">
                    If you've played before, enter your User ID to continue with the same identity.
                  </small>
                </div>

                <div class="d-grid">
                  <button
                    type="submit"
                    class="btn btn-primary"
                    [disabled]="loginForm.invalid || isLoading"
                  >
                    <span *ngIf="isLoading" class="loading-spinner me-2"></span>
                    <i *ngIf="!isLoading" class="bi bi-box-arrow-in-right me-2"></i>
                    {{ isLoading ? 'Logging in...' : 'Start Playing' }}
                  </button>
                </div>
              </form>

              <div class="alert alert-danger mt-3" *ngIf="errorMessage">
                <i class="bi bi-exclamation-triangle me-2"></i>
                {{ errorMessage }}
              </div>

              <div class="mt-4 text-center">
                <small class="text-muted">
                  <i class="bi bi-info-circle me-1"></i>
                  ChipMate helps you track poker game buy-ins, cashouts, and debts easily.
                </small>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: []
})
export class LoginComponent {
  loginForm: FormGroup;
  isLoading = false;
  errorMessage = '';

  constructor(
    private formBuilder: FormBuilder,
    private apiService: ApiService,
    private router: Router
  ) {
    this.loginForm = this.formBuilder.group({
      name: ['', [Validators.required, Validators.minLength(2)]],
      user_id: ['']
    });
  }

  onSubmit(): void {
    if (this.loginForm.valid) {
      this.isLoading = true;
      this.errorMessage = '';

      const authRequest: AuthRequest = {
        name: this.loginForm.value.name.trim()
      };

      if (this.loginForm.value.user_id) {
        authRequest.user_id = parseInt(this.loginForm.value.user_id, 10);
      }

      this.apiService.login(authRequest).subscribe({
        next: (response) => {
          this.apiService.setCurrentUser(response.user);
          this.isLoading = false;

          // Redirect to current game if user has one, otherwise to home
          if (response.user.current_game_id) {
            this.router.navigate(['/game', response.user.current_game_id]);
          } else {
            this.router.navigate(['/home']);
          }
        },
        error: (error) => {
          this.isLoading = false;
          this.errorMessage = error.error?.message || 'Login failed. Please try again.';
        }
      });
    }
  }
}