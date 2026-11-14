const fs = require('node:fs');
const path = require('node:path');
const {
  initializeTestEnvironment,
  assertSucceeds,
  assertFails,
} = require('@firebase/rules-unit-testing');
const { Timestamp } = require('firebase/firestore');
const { before, after, beforeEach, test } = require('node:test');

const PROJECT_ID = 'demo-dautu';
const ADMIN_EMAIL = 'nguyenanhtuan081196@gmail.com';
const USER_EMAIL = 'user@example.com';
const OTHER_EMAIL = 'other@example.com';
let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: {
      rules: fs.readFileSync(path.join(__dirname, '..', 'firestore.rules'), 'utf8'),
    },
  });
});
after(async () => testEnv.cleanup());
beforeEach(async () => {
  // Seed and clear only the documents used by this suite inside a fresh
  // privileged context. Do not call clearFirestore(), which initializes a
  // Firestore client before the rules-disabled context is created.
  await testEnv.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    await Promise.all([
      'allowed_users/user@example.com',
      'allowed_users/other@example.com',
      'allowed_users/nguyenanhtuan081196@gmail.com',
      'watchlists/owner-uid',
      'watchlists/stranger-uid',
    ].map((documentPath) => db.doc(documentPath).delete()));

    await db.doc('allowed_users/user@example.com').set({
      email: USER_EMAIL, role: 'user',
      expiresAt: Timestamp.fromMillis(Date.now() + 2 * 86400000),
      createdBy: ADMIN_EMAIL, createdSource: 'admin_console', updatedBy: ADMIN_EMAIL,
    });
    await db.doc('allowed_users/nguyenanhtuan081196@gmail.com').set({
      email: ADMIN_EMAIL, role: 'admin',
      expiresAt: Timestamp.fromMillis(Date.now() + 30 * 86400000),
      createdBy: ADMIN_EMAIL, createdSource: 'admin_console', updatedBy: ADMIN_EMAIL,
    });
  });
});

function signedIn(email, uid = 'uid-1', verified = true) {
  return testEnv.authenticatedContext(uid, {
    email, email_verified: verified,
  }).firestore();
}

test('unauthenticated users cannot read account records', async () => {
  await assertFails(testEnv.unauthenticatedContext().firestore()
    .doc('allowed_users/user@example.com').get());
});
test('a user can read only their own account document', async () => {
  await assertSucceeds(signedIn(USER_EMAIL).doc('allowed_users/user@example.com').get());
  await assertFails(signedIn(USER_EMAIL).doc('allowed_users/other@example.com').get());
});
test('only the fixed verified admin email can list account records', async () => {
  await assertFails(signedIn(USER_EMAIL).collection('allowed_users').get());
  await assertFails(signedIn(ADMIN_EMAIL, 'admin-unverified', false).collection('allowed_users').get());
  await assertSucceeds(signedIn(ADMIN_EMAIL, 'admin-verified', true).collection('allowed_users').get());
});
test('users cannot create any allowed_users document, including their own', async () => {
  const db = signedIn(OTHER_EMAIL);
  await assertFails(db.doc('allowed_users/other@example.com').set({
    email: OTHER_EMAIL, role: 'user',
    expiresAt: Timestamp.fromMillis(Date.now() + 6 * 86400000),
  }));
});
test('non-admin self-registration attempts are rejected regardless of requested role or expiry', async () => {
  const ref = signedIn(OTHER_EMAIL).doc('allowed_users/other@example.com');
  const future = Timestamp.fromMillis(Date.now() + 6 * 86400000);
  await assertFails(ref.set({ email: OTHER_EMAIL, role: 'admin', expiresAt: future }));
  await assertFails(ref.set({ email: OTHER_EMAIL, role: 'user', expiresAt: future, extra: true }));
  await assertFails(ref.set({
    email: OTHER_EMAIL, role: 'user',
    expiresAt: Timestamp.fromMillis(Date.now() - 1000),
  }));
  await assertFails(ref.set({
    email: OTHER_EMAIL, role: 'user',
    expiresAt: Timestamp.fromMillis(Date.now() + 8 * 86400000),
  }));
});
test('users cannot update or delete account records', async () => {
  const db = signedIn(USER_EMAIL);
  await assertFails(db.doc('allowed_users/user@example.com').update({ role: 'admin' }));
  await assertFails(db.doc('allowed_users/user@example.com').set({
    email: USER_EMAIL,
    role: 'user',
    expiresAt: Timestamp.fromMillis(Date.now() + 6 * 86400000),
  }));
  await assertFails(db.doc('allowed_users/user@example.com').delete());
});
test('verified Admin can create and update only Admin-provenance legacy records', async () => {
  const db = signedIn(ADMIN_EMAIL, 'admin-verified', true);
  const ref = db.doc('allowed_users/other@example.com');
  const expiresAt = Timestamp.fromMillis(Date.now() + 30 * 86400000);
  await assertSucceeds(ref.set({
    email: OTHER_EMAIL, role: 'user', expiresAt,
    createdBy: ADMIN_EMAIL, createdSource: 'admin_console', updatedBy: ADMIN_EMAIL,
  }));
  await assertSucceeds(ref.update({
    expiresAt: Timestamp.fromMillis(Date.now() + 60 * 86400000),
    updatedBy: ADMIN_EMAIL,
  }));
  await assertSucceeds(ref.update({ role: 'admin', updatedBy: ADMIN_EMAIL }));
  await assertFails(ref.update({ createdBy: OTHER_EMAIL }));
  await assertFails(ref.delete());
});
test('watchlists are restricted to the owning Firebase UID', async () => {
  const owner = signedIn(USER_EMAIL, 'owner-uid');
  const stranger = signedIn(OTHER_EMAIL, 'stranger-uid');
  await assertSucceeds(owner.doc('watchlists/owner-uid').set({ symbols: ['FPT'] }));
  await assertFails(stranger.doc('watchlists/owner-uid').get());
});
