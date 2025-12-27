import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ApiService } from '../../services/api.service';
import { Game } from '../../models/game.model';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="container-fluid mt-4">
      <!-- Header -->
      <div class="row mb-4">
        <div class="col-12">
          <div class="card game-card">
            <div class="card-header">
              <h4 class="mb-0">
                <i class="bi bi-shield-check me-2"></i>
                Admin Dashboard
              </h4>
            </div>
          </div>
        </div>
      </div>

      <!-- Stats Cards -->
      <div class="row mb-4" *ngIf="stats">
        <div class="col-md-3 mb-3">
          <div class="card text-center game-card">
            <div class="card-body">
              <i class="bi bi-controller display-4 text-primary"></i>
              <h3 class="mt-2">{{ stats.total_games }}</h3>
              <p class="text-muted mb-0">Total Games</p>
              <small class="text-success">{{ stats.active_games }} active</small>
            </div>
          </div>
        </div>
        <div class="col-md-3 mb-3">
          <div class="card text-center game-card">
            <div class="card-body">
              <i class="bi bi-people display-4 text-success"></i>
              <h3 class="mt-2">{{ stats.total_players }}</h3>
              <p class="text-muted mb-0">Total Players</p>
              <small class="text-success">{{ stats.active_players }} active</small>
            </div>
          </div>
        </div>
        <div class="col-md-3 mb-3">
          <div class="card text-center game-card">
            <div class="card-body">
              <i class="bi bi-arrow-left-right display-4 text-info"></i>
              <h3 class="mt-2">{{ stats.total_transactions }}</h3>
              <p class="text-muted mb-0">Transactions</p>
              <small class="text-muted">{{ stats.avg_transactions_per_game }} avg/game</small>
            </div>
          </div>
        </div>
        <div class="col-md-3 mb-3">
          <div class="card text-center game-card">
            <div class="card-body">
              <i class="bi bi-credit-card display-4 text-warning"></i>
              <h3 class="mt-2">{{ stats.total_debts }}</h3>
              <p class="text-muted mb-0">Debt Records</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Filter Tabs -->
      <div class="row mb-3">
        <div class="col-12">
          <ul class="nav nav-pills">
            <li class="nav-item">
              <button class="nav-link" [class.active]="statusFilter === null" (click)="filterByStatus(null)">
                All Games
              </button>
            </li>
            <li class="nav-item">
              <button class="nav-link" [class.active]="statusFilter === 'active'" (click)="filterByStatus('active')">
                Active
              </button>
            </li>
            <li class="nav-item">
              <button class="nav-link" [class.active]="statusFilter === 'ended'" (click)="filterByStatus('ended')">
                Ended
              </button>
            </li>
            <li class="nav-item">
              <button class="nav-link" [class.active]="statusFilter === 'expired'" (click)="filterByStatus('expired')">
                Expired
              </button>
            </li>
          </ul>
        </div>
      </div>

      <!-- Games List -->
      <div class="row">
        <div class="col-12">
          <div class="card game-card">
            <div class="card-header d-flex justify-content-between align-items-center">
              <h5 class="mb-0">
                <i class="bi bi-list-ul me-2"></i>
                Games ({{ games.length }})
              </h5>
              <button class="btn btn-sm btn-primary" (click)="refreshData()">
                <i class="bi bi-arrow-clockwise me-1"></i>
                Refresh
              </button>
            </div>
            <div class="card-body">
              <div class="table-responsive">
                <table class="table table-hover">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Host</th>
                      <th>Status</th>
                      <th>Players</th>
                      <th>Created</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr *ngFor="let game of games">
                      <td>
                        <strong>{{ game.code }}</strong>
                      </td>
                      <td>{{ game.host_name }}</td>
                      <td>
                        <span class="badge" [class]="getStatusBadgeClass(game.status)">
                          {{ game.status | titlecase }}
                        </span>
                      </td>
                      <td>
                        <i class="bi bi-people me-1"></i>
                        {{ game.player_count || 0 }}
                      </td>
                      <td>{{ formatDate(game.created_at) }}</td>
                      <td>
                        <div class="btn-group btn-group-sm">
                          <button class="btn btn-outline-primary" (click)="viewGame(game.id)" title="View Game">
                            <i class="bi bi-eye"></i>
                          </button>
                          <button class="btn btn-outline-danger" (click)="confirmDestroyGame(game)" title="Destroy Game">
                            <i class="bi bi-trash"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                    <tr *ngIf="games.length === 0">
                      <td colspan="6" class="text-center text-muted">
                        <i class="bi bi-inbox display-4 d-block mb-2"></i>
                        No games found
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Messages -->
    <div class="position-fixed top-0 end-0 p-3" style="z-index: 11">
      <div class="toast align-items-center text-white bg-success border-0" [class.show]="showSuccessToast" role="alert">
        <div class="d-flex">
          <div class="toast-body">
            {{ successMessage }}
          </div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" (click)="showSuccessToast = false"></button>
        </div>
      </div>
      <div class="toast align-items-center text-white bg-danger border-0" [class.show]="showErrorToast" role="alert">
        <div class="d-flex">
          <div class="toast-body">
            {{ errorMessage }}
          </div>
          <button type="button" class="btn-close btn-close-white me-2 m-auto" (click)="showErrorToast = false"></button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .toast.show {
      display: block !important;
    }
  `]
})
export class AdminDashboardComponent implements OnInit {
  games: any[] = [];
  stats: any = null;
  statusFilter: string | null = null;

  // Messages
  successMessage = '';
  errorMessage = '';
  showSuccessToast = false;
  showErrorToast = false;

  constructor(
    private apiService: ApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    this.loadStats();
    this.loadGames();
  }

  loadStats(): void {
    this.apiService.getSystemStats().subscribe({
      next: (stats) => {
        this.stats = stats;
      },
      error: (error) => {
        this.showError('Failed to load system stats');
      }
    });
  }

  loadGames(): void {
    this.apiService.listAllGames(this.statusFilter || undefined).subscribe({
      next: (response) => {
        this.games = response.games;
      },
      error: (error) => {
        this.showError('Failed to load games');
      }
    });
  }

  filterByStatus(status: string | null): void {
    this.statusFilter = status;
    this.loadGames();
  }

  refreshData(): void {
    this.loadStats();
    this.loadGames();
  }

  viewGame(gameId: string): void {
    this.router.navigate(['/game', gameId]);
  }

  confirmDestroyGame(game: any): void {
    if (confirm(`Are you sure you want to permanently delete game ${game.code}? This action cannot be undone and will delete all related data.`)) {
      this.apiService.destroyGame(game.id).subscribe({
        next: (response) => {
          this.showSuccess(`Game ${game.code} destroyed successfully`);
          this.loadGames();
          this.loadStats();
        },
        error: (error) => {
          this.showError(error.error?.message || 'Failed to destroy game');
        }
      });
    }
  }

  getStatusBadgeClass(status: string): string {
    switch (status) {
      case 'active': return 'bg-success';
      case 'ended': return 'bg-secondary';
      case 'expired': return 'bg-danger';
      default: return 'bg-secondary';
    }
  }

  formatDate(dateString: string): string {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  }

  showSuccess(message: string): void {
    this.successMessage = message;
    this.showSuccessToast = true;
    setTimeout(() => {
      this.showSuccessToast = false;
    }, 5000);
  }

  showError(message: string): void {
    this.errorMessage = message;
    this.showErrorToast = true;
    setTimeout(() => {
      this.showErrorToast = false;
    }, 5000);
  }
}
