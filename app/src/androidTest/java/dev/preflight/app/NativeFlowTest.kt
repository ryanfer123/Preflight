package dev.preflight.app

import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.closeSoftKeyboard
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.action.ViewActions.*
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.*
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.preflight.app.domain.*
import dev.preflight.app.ui.MainActivity
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Offline instrumented journeys. Fake repository replaces only transport, never UI behavior. */
@RunWith(AndroidJUnit4::class)
class NativeFlowTest {
    private lateinit var app: PreflightApplication
    private lateinit var previousFactory: (String) -> PreflightRepository
    private lateinit var repository: OfflineRepository

    @Before fun setup() {
        app = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext as PreflightApplication
        previousFactory = app.repositoryFactory
        repository = OfflineRepository()
        app.repositoryFactory = { repository }
    }
    @After fun tearDown() { app.repositoryFactory = previousFactory }

    @Test fun sampleUploadEvidenceAndRotation() {
        ActivityScenario.launch(MainActivity::class.java).use { scenario ->
            onView(withText("Try a sample invoice")).perform(scrollTo(), click())
            onView(withText("Changed bank account")).perform(click())
            onView(withText("Check invoice")).perform(scrollTo(), click())
            waitForText("× BLOCK")
            onView(withText("× BLOCK")).check(matches(isDisplayed()))
            onView(withText("Could not be verified")).perform(scrollTo()).check(matches(isDisplayed()))
            onView(withText("Show evidence")).perform(scrollTo(), click())
            onView(withText("654321")).check(matches(isDisplayed()))
            scenario.recreate()
            onView(withText("Invoice check")).check(matches(isDisplayed()))
            assertEquals(1, repository.checks)
        }
    }

    @Test fun approvalRequiresExplicitConfirmation() {
        ActivityScenario.launch(MainActivity::class.java).use {
            waitForText("Try a sample invoice")
            onView(withId(R.id.nav_ledger)).perform(click())
            waitForText("Approve bank details")
            onView(withText("Approve bank details")).perform(scrollTo(), click())
            onView(withId(R.id.approver_name)).perform(scrollTo(), replaceText("Test owner"))
            closeSoftKeyboard()
            onView(withText("Approve and remember")).perform(scrollTo(), click())
            waitForText("Could not complete the request")
            assertFalse(repository.approved)
            onView(withId(R.id.approver_name)).perform(scrollTo(), replaceText("Test owner"))
            closeSoftKeyboard()
            onView(withId(R.id.approval_checkbox)).perform(scrollTo(), click())
            onView(withText("Approve and remember")).perform(scrollTo(), click())
            waitForText("Bank details remembered. Existing reports remain unchanged.")
            assertTrue(repository.approved)
            assertEquals("Test owner", repository.actor)
        }
    }

    private fun waitForText(text: String) {
        val deadline = System.currentTimeMillis() + 5000
        while (true) {
            try { onView(withText(text)).check(matches(withText(text))); return }
            catch (error: AssertionError) { if (System.currentTimeMillis() >= deadline) throw error }
            catch (error: androidx.test.espresso.NoMatchingViewException) {
                if (System.currentTimeMillis() >= deadline) throw error
            }
            Thread.sleep(50)
        }
    }

    private class OfflineRepository : PreflightRepository {
        var approved = false
        var actor = ""
        var checks = 0
        private val account = "account:654321|ifsc:sbin0001234"
        override fun connect() = Session("FakeExtractor")
        override fun vendors() = listOf(Vendor(1, "Acme", listOf("acme.example"),
            listOf(BankAccount(account, approved, actor.ifBlank { null }, if (approved) "2026-01-01" else null)), emptyList()))
        override fun check(invoice: Attachment, email: Attachment?, vendorId: Long?): Report {
            checks++
            return report("sample")
        }
        override fun report(id: String) = Report(id, "bank-change.pdf", Verdict.BLOCK, 10,
            listOf(Finding("bank_change", "critical", "observed", "Payment details differ from approved accounts",
                listOf(Evidence("bank.account_number", "654321", 1)))),
            listOf("sender.authentication_trust"), listOf("critical_finding"), "FakeExtractor", null,
            InvoiceSummary("Acme", "PF-TEST", "118.001", "INR"))
        override fun approve(vendorId: Long, account: String, actor: String, confirmed: Boolean) {
            require(confirmed && actor.isNotBlank()) { "Confirm independent verification and enter your name." }
            this.approved = true; this.actor = actor
        }
    }
}
