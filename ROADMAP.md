# Recipe Book App - Development Roadmap

## Current Status (v1.0 Beta)
✅ Multi-user authentication
✅ Recipe scraping from URLs
✅ Manual recipe entry with Quick Paste
✅ Edit recipes
✅ Print functionality
✅ Settings page
✅ Search & sort
✅ Categories & notes
✅ Mobile responsive

## Phase 1: Premium Features (Next Priority)

### Option A: Theme Customization ($5 premium)
- [ ] Color picker for primary color (butter yellow default)
- [ ] Color picker for text color (dark green default)
- [ ] Font selection (3-5 options)
- [ ] Preview before applying
- [ ] Save theme per user

### Option B: Recipe Sharing ($5 premium)
- [ ] Generate shareable link (read-only)
- [ ] Share via email
- [ ] Public recipe page (no login required)
- [ ] Optional: Allow others to copy to their account

### Option C: PDF Export ($5 premium)
- [ ] Export single recipe as PDF
- [ ] Export multiple recipes as PDF
- [ ] Custom formatting options
- [ ] Include/exclude notes option

### Option D: Recipe Collections ($5 premium)
- [ ] Create folders/collections
- [ ] Organize recipes into collections
- [ ] Share entire collections
- [ ] Meal planning view

**Decision needed:** Which premium feature(s) to build first?

## Phase 2: Monetization

### Donation System (Free tier)
- [ ] Add Ko-fi button in header
- [ ] Add "Support" section in settings
- [ ] Track donations (optional)

### Premium Upgrade Flow
- [ ] "Upgrade to Premium" button
- [ ] Payment integration (Stripe/Gumroad)
- [ ] Premium badge display
- [ ] Feature unlocking system

**Decision needed:** Ko-fi only, or full payment system?

## Phase 3: PWA Offline Mode

### Service Worker
- [ ] Cache app shell (HTML/CSS/JS)
- [ ] Cache recipe data
- [ ] Offline indicator
- [ ] Sync when back online

### IndexedDB
- [ ] Store recipes locally
- [ ] Conflict resolution (last write wins)
- [ ] Background sync

### Install Prompt
- [ ] "Add to Home Screen" prompt
- [ ] Custom app icon
- [ ] Splash screen

**Estimated time:** 4-6 hours

## Phase 4: Cloud Deployment

### Hosting Options
**Option A: Railway ($5/month)**
- Pros: Easy, auto-deploy from GitHub
- Cons: Monthly cost

**Option B: Render (Free tier)**
- Pros: Free, auto-deploy
- Cons: Sleeps after inactivity, slower

**Option C: DigitalOcean ($6/month)**
- Pros: Full control, fast
- Cons: More setup, manual deploys

**Decision needed:** Which hosting service?

### Domain Name
- [ ] Purchase domain (e.g., myrecipebook.app)
- [ ] Configure DNS
- [ ] Setup HTTPS (Let's Encrypt)

**Decision needed:** Domain name? Budget?

### Database Migration
- [ ] Move from JSON files to PostgreSQL/SQLite
- [ ] Migration script for existing users
- [ ] Backup strategy

## Phase 5: Additional Features (Backlog)

### Recipe Features
- [ ] Recipe scaling (2x, 3x servings)
- [ ] Nutrition info (API integration)
- [ ] Recipe ratings/favorites
- [ ] Recipe tags (beyond categories)
- [ ] Cooking timer integration

### Social Features
- [ ] Follow other users
- [ ] Recipe comments
- [ ] Recipe variations/forks
- [ ] Community recipes

### Meal Planning
- [ ] Weekly meal planner
- [ ] Grocery list generation
- [ ] Ingredient inventory tracking

### Import/Export
- [ ] Import from Paprika
- [ ] Import from other apps
- [ ] Bulk import from CSV
- [ ] Export all data (GDPR compliance)

## Technical Debt

### Code Quality
- [ ] Add unit tests
- [ ] Add integration tests
- [ ] Error handling improvements
- [ ] Logging system

### Security
- [ ] Rate limiting (prevent abuse)
- [ ] CSRF protection
- [ ] Input sanitization review
- [ ] Password reset flow
- [ ] Email verification

### Performance
- [ ] Recipe pagination (if >100 recipes)
- [ ] Image optimization (if adding photos)
- [ ] Caching strategy
- [ ] Database indexing

## Questions for You

1. **Premium features:** Which should we build first?
   - Theme customization?
   - Recipe sharing?
   - PDF export?
   - Collections/folders?

2. **Monetization:** 
   - Ko-fi donations only?
   - Or full premium upgrade system?

3. **Deployment:**
   - Which hosting service?
   - Domain name ideas?
   - Budget per month?

4. **Timeline:**
   - Launch date goal?
   - MVP features vs nice-to-haves?

5. **Target audience:**
   - General public?
   - Privacy-focused users?
   - Budget-conscious users?
   - Tech-savvy users?

## Next Session Plan

When you're back, tell me:
1. Which phase to work on (1, 2, 3, or 4)
2. Any specific features you want
3. Any design preferences
4. Budget/timeline constraints

Then I'll build exactly what you need!

---

**Current files:**
- `recipe_server_multiuser.py` - Main app (67KB)
- `users.json` - User accounts
- `sessions.json` - Active sessions  
- `user_recipes/` - Per-user recipes

**GitHub:** https://github.com/blondegedu/recipe-book
**Status:** Ready for deployment or feature additions
