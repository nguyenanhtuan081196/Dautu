"""Tests for Admin account management endpoints and invariants."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException

from app.api import main


class FakeCursor(list):
    def sort(self, key, direction):
        return FakeCursor(sorted(self, key=lambda row: row.get(key) or "", reverse=direction < 0))
    def limit(self, amount):
        return FakeCursor(self[:amount])


class FakeUsers:
    def __init__(self, rows):
        self.rows={row["email"]:dict(row) for row in rows}
    def find(self, query, projection):
        return FakeCursor(self.rows.values())
    def find_one(self, query):
        row=self.rows.get(query["email"])
        return dict(row) if row else None
    def update_one(self, query, update):
        self.rows[query["email"]].update(update["$set"])
    def count_documents(self, query):
        return sum(1 for row in self.rows.values()
                   if row.get("role")==query["role"] and row.get("status")==query["status"]
                   and row.get("email")!=query["email"]["$ne"])


class FakeAudit:
    def __init__(self): self.events=[]
    def insert_one(self, event): self.events.append(event)


class AdminEndpointTests(unittest.TestCase):
    def setUp(self):
        now=datetime.now(timezone.utc)
        self.users=FakeUsers([
            {"email":"admin@example.com","role":"admin","status":"active","created_at":now,"expired_at":None},
            {"email":"member@example.com","role":"user","status":"active","created_at":now,"expired_at":now+timedelta(days=3)},
        ])
        self.db=SimpleNamespace(users=self.users,users_admin_audit=FakeAudit())
        self.actor={"email":"admin@example.com","app_role":"admin"}

    def test_list_users_returns_allowlisted_account_fields(self):
        rows=main.admin_list_users(self.actor,self.db,500)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["email"],"admin@example.com")
        self.assertNotIn("_id",rows[0])
        self.assertNotIn("firebase_uid",rows[0])

    def test_lock_unlock_and_audit_user(self):
        locked=main.admin_update_status(main.AdminStatusUpdate(status="locked"),"member@example.com",self.actor,self.db)
        self.assertEqual(locked["status"],"locked")
        unlocked=main.admin_update_status(main.AdminStatusUpdate(status="active"),"member@example.com",self.actor,self.db)
        self.assertEqual(unlocked["status"],"active")
        self.assertEqual(len(self.db.users_admin_audit.events),2)

    def test_cannot_lock_last_admin_or_self(self):
        with self.assertRaises(HTTPException) as error:
            main.admin_update_status(main.AdminStatusUpdate(status="locked"),"admin@example.com",self.actor,self.db)
        self.assertEqual(error.exception.status_code,409)
        with self.assertRaises(HTTPException) as error:
            main.admin_update_status(main.AdminStatusUpdate(status="locked"),"member@example.com",self.actor,self.db)
        self.assertEqual(error.exception.status_code,409)

    def test_extend_user_subscription_and_reject_admin(self):
        result=main.admin_extend_user(main.AdminExtendRequest(days=30),"member@example.com",self.actor,self.db)
        self.assertGreater(datetime.fromisoformat(result["expired_at"]),datetime.now(timezone.utc)+timedelta(days=29))
        with self.assertRaises(HTTPException) as error:
            main.admin_extend_user(main.AdminExtendRequest(days=30),"admin@example.com",self.actor,self.db)
        self.assertEqual(error.exception.status_code,409)

    def test_role_change_requires_future_expiry_for_user(self):
        self.users.rows["member@example.com"].update({"role":"guest","expired_at":None})
        with self.assertRaises(HTTPException) as error:
            main.admin_update_role(main.AdminRoleUpdate(role="user"),"member@example.com",self.actor,self.db)
        self.assertEqual(error.exception.status_code,422)
        expiry=datetime.now(timezone.utc)+timedelta(days=30)
        result=main.admin_update_role(main.AdminRoleUpdate(role="user",expired_at=expiry),"member@example.com",self.actor,self.db)
        self.assertEqual(result["role"],"user")
        self.assertIsNotNone(result["expired_at"])

    def test_role_change_cannot_demote_self_or_last_admin(self):
        with self.assertRaises(HTTPException) as error:
            main.admin_update_role(main.AdminRoleUpdate(role="guest"),"admin@example.com",self.actor,self.db)
        self.assertEqual(error.exception.status_code,409)

    def test_missing_user_and_invalid_email_are_rejected(self):
        with self.assertRaises(HTTPException) as error:
            main._admin_target(self.db,"not-an-email")
        self.assertEqual(error.exception.status_code,422)
        with self.assertRaises(HTTPException) as error:
            main._admin_target(self.db,"missing@example.com")
        self.assertEqual(error.exception.status_code,404)

    def test_all_admin_routes_require_admin_dependency(self):
        protected=[route for route in main.app.routes if getattr(route,"path","").startswith("/api/admin/")]
        self.assertEqual(len(protected),4)
        for route in protected:
            names={getattr(dep.call,"__name__",None) for dep in route.dependant.dependencies}
            self.assertIn("require_admin",names)


if __name__=="__main__":
    unittest.main()
