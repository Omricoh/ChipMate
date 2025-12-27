import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterModule, Router, NavigationEnd } from '@angular/router';
import { NavbarComponent } from './components/navbar/navbar.component';
import { ApiService } from './services/api.service';
import { filter, take } from 'rxjs/operators';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterModule, NavbarComponent],
  template: `
    <div class="main-container">
      <app-navbar></app-navbar>
      <main class="flex-grow-1">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: []
})
export class AppComponent implements OnInit {
  title = 'ChipMate - Poker Game Manager';

  constructor(
    private apiService: ApiService,
    private router: Router
  ) {}

  ngOnInit(): void {
    // Wait for the first navigation to complete before checking for auto-redirect
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd),
      take(1)
    ).subscribe(() => {
      this.checkAndRedirectToActiveGame();
    });
  }

  private checkAndRedirectToActiveGame(): void {
    const currentUser = this.apiService.getCurrentUser();
    
    // Only proceed if user is logged in and has a current game
    if (!currentUser || !currentUser.current_game_id) {
      return;
    }

    const currentRoute = this.router.url;
    
    // Don't redirect if already on the game page or login page
    const isOnGamePage = currentRoute.startsWith('/game/');
    const isOnLoginPage = currentRoute.startsWith('/login');
    
    if (isOnGamePage || isOnLoginPage) {
      return;
    }

    // Verify the game is still active before redirecting
    this.apiService.getGame(currentUser.current_game_id).subscribe({
      next: (game) => {
        if (game.status === 'active') {
          console.log('Auto-redirecting to active game:', currentUser.current_game_id);
          this.router.navigate(['/game', currentUser.current_game_id]);
        } else {
          // Game is no longer active, clear the reference
          console.log('Game is no longer active, clearing reference');
          currentUser.current_game_id = undefined;
          this.apiService.setCurrentUser(currentUser);
        }
      },
      error: (err) => {
        // Game not found or error occurred, clear the reference
        console.error('Error fetching game, clearing reference:', err);
        currentUser.current_game_id = undefined;
        this.apiService.setCurrentUser(currentUser);
      }
    });
  }
}