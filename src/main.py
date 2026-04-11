"""
Catastrophe Analyzer - Main CLI Interface
Orchestrates news scraping, entity extraction, stock analysis, and signal generation
"""

import sys
import os
import argparse
from datetime import datetime
import json
import io
import contextlib
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_scraper import NewsScraper
from entity_extractor import EntityExtractor
from stock_analyzer import StockAnalyzer
from signal_generator import SignalGenerator
from database_manager import DatabaseManager
from impact_triage import ImpactTriage
from alert_manager import AlertManager
from service_runtime import run_service_loop


class CatastropheAnalyzerApp:
    """
    Main application orchestrating all modules
    """

    def __init__(self):
        """Initialize all components"""
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        self.config_path = os.path.join(self.repo_root, 'config', 'settings.json')
        self.data_dir = os.path.join(self.repo_root, 'data')

        self.settings = self._load_settings()

        mock_env = os.environ.get("CATASTROPHE_ANALYZER_USE_MOCK_DATA", "").strip()
        if mock_env == "":
            mock_env = os.environ.get("BREACH_ANALYZER_USE_MOCK_DATA", "").strip()

        self.news_scraper = NewsScraper(config_path=self.config_path)
        self.entity_extractor = EntityExtractor(config_path=self.config_path)
        self.stock_analyzer = StockAnalyzer(
            use_mock=(
                mock_env.lower() in ["1", "true", "yes"]
                if mock_env != ""
                else self.settings.get('stock_analysis', {}).get('use_mock_data', True)
            ),
            stock_analysis_config=self.settings.get("stock_analysis") or {},
        )
        self.signal_generator = SignalGenerator(config_path=self.config_path)
        self.db = DatabaseManager(data_dir=self.data_dir)
        self.impact_triage = ImpactTriage(config=self.settings)

        self.current_articles = []
        self.current_entities = []
        self.current_analyses = []
        self.current_signals = []

    def _load_settings(self) -> Dict:
        """Load settings.json with safe defaults."""
        defaults = {}
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return defaults

    @staticmethod
    def _severity_rank(value: str) -> int:
        mapping = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
        return mapping.get((value or "").upper(), 2)

    def _financial_distress_assessment(
        self,
        title: str,
        summary: str,
        event_category: str,
    ) -> Dict:
        """
        Estimate probability that an event will trigger financial distress pressure.

        The score is a heuristic (0-100) based on language cues in title/summary.
        """
        content = f"{title} {summary}".lower()
        score = 15
        reasons: List[str] = []

        if event_category == "cybersecurity":
            weighted_markers = [
                ("ransomware", 22, "Ransomware often causes direct operational/financial disruption"),
                ("wiper", 24, "Wiper-style activity implies destructive impact"),
                ("destructive malware", 24, "Destructive malware often implies prolonged operational recovery"),
                ("material cybersecurity incident", 28, "Material incident language implies meaningful financial risk"),
                ("operations disrupted", 20, "Operational disruption can pressure revenue and margin"),
                ("service outage", 14, "Customer-facing outage may create churn/penalties"),
                ("class action", 12, "Legal follow-on risk increases expected costs"),
                ("regulator investigation", 14, "Regulatory investigations can lead to fines/compliance spend"),
                ("8-k", 10, "8-K disclosure language usually indicates materiality"),
                ("sec filing", 10, "SEC filing language usually indicates materiality"),
                ("unauthorized access", 12, "Unauthorized access can imply incident containment/remediation spend"),
                ("exfiltration", 14, "Data exfiltration raises legal and remediation costs"),
                ("supply chain attack", 18, "Supply-chain compromise can broaden blast radius and downtime"),
                ("credentials leaked", 10, "Credential leaks can drive remediation and fraud costs"),
                ("millions", 8, "Large-scale impact tends to elevate downstream cost"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)

            positive_offsets = [
                ("services restored", 12, "Service restoration language lowers near-term disruption risk"),
                ("no evidence of exfiltration", 12, "No-exfiltration statements can reduce expected downstream liability"),
                ("no customer data accessed", 10, "Limited customer-data impact lowers expected follow-on costs"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "clinical_regulatory_binary":
            weighted_markers = [
                ("complete response letter", 32, "CRL usually delays/blocks commercialization"),
                ("clinical hold", 28, "Clinical hold can pause trial progression and timelines"),
                ("partial clinical hold", 22, "Partial hold still constrains trial operations and timelines"),
                ("trial hold", 28, "Trial hold can pause trial progression and timelines"),
                ("rejected", 18, "Regulatory rejection raises uncertainty and delay risk"),
                ("refuse to file", 24, "Refuse-to-file meaningfully delays path to market"),
                ("missed primary endpoint", 26, "Missed endpoint weakens program value"),
                ("did not meet endpoint", 24, "Endpoint miss materially weakens value narrative"),
                ("terminated trial", 24, "Trial termination can reset expected commercialization value"),
                ("failed", 16, "Negative trial language indicates development risk"),
                ("adverse event", 14, "Safety issues can impair approval/commercial outlook"),
                ("safety signal", 16, "Safety signals can trigger restrictions or delay"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)

            positive_offsets = [
                ("fda approval", 22, "Approval is a de-risking catalyst"),
                ("approved by the fda", 22, "Approval is a de-risking catalyst"),
                ("met primary endpoint", 16, "Positive efficacy readout lowers distress risk"),
                ("positive topline", 12, "Positive topline readout lowers distress risk"),
                ("top-line results met", 12, "Positive topline readout lowers distress risk"),
                ("priority review", 8, "Priority review can reduce time-to-decision uncertainty"),
                ("breakthrough therapy", 10, "Breakthrough designation can improve regulatory pathway confidence"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "product_safety_recall":
            weighted_markers = [
                ("recall", 22, "Recall language signals direct product and liability risk"),
                ("class i recall", 30, "Class I recall implies highest-severity safety exposure"),
                ("class 1 recall", 30, "Class I recall implies highest-severity safety exposure"),
                ("grounding", 24, "Grounding can halt core revenue operations"),
                ("do not use", 24, "Do-not-use language implies immediate customer/product disruption"),
                ("stop sale", 22, "Stop-sale actions can rapidly pressure near-term sales"),
                ("market withdrawal", 18, "Market withdrawals indicate direct product revenue disruption"),
                ("safety alert", 16, "Safety alerts increase remediation and legal exposure"),
                ("warning letter", 16, "Regulatory warning letters can constrain operations"),
                ("defect", 14, "Defect disclosures can drive replacement and litigation costs"),
                ("contamination", 18, "Contamination events can trigger broad product withdrawals"),
                ("production halt", 20, "Production halts directly pressure near-term revenue"),
                ("injury", 16, "Injury reports increase legal and reputational risk"),
                ("fatality", 20, "Fatality language increases legal, regulatory, and reputational risk"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)

        elif event_category == "fraud_accounting_enforcement":
            weighted_markers = [
                ("indictment", 30, "Indictments imply severe legal and governance overhang"),
                ("criminal charges", 28, "Criminal charges elevate tail risk and distraction"),
                ("guilty plea", 26, "Guilty pleas often precede costly remediation and oversight"),
                ("wire fraud", 26, "Wire-fraud allegations signal acute enforcement exposure"),
                ("securities fraud", 28, "Securities-fraud allegations directly threaten credibility and access to capital"),
                ("accounting fraud", 28, "Accounting-fraud language implies restatement and control failure risk"),
                ("sec charges", 26, "SEC charges usually force disclosure, defense spend, and remediation"),
                ("sec alleges", 24, "SEC allegations increase regulatory resolution uncertainty"),
                ("enforcement action", 22, "Enforcement actions often include penalties and conduct remedies"),
                ("cease and desist", 18, "Cease-and-desist remedies can constrain business conduct"),
                ("cease-and-desist", 18, "Cease-and-desist remedies can constrain business conduct"),
                ("civil complaint", 20, "Civil complaints increase litigation duration and cost risk"),
                ("restatement", 24, "Restatements often reset earnings quality and analyst trust"),
                ("material weakness", 22, "Material weakness language signals control and reporting risk"),
                ("internal control", 18, "Internal-control failures can widen restatement scope"),
                ("wells notice", 24, "Wells notices usually precede charged enforcement outcomes"),
                ("subpoena", 14, "Subpoenas imply investigative process and legal spend"),
                ("auditor resignation", 20, "Auditor resignations can trigger credibility shocks"),
                ("going concern", 18, "Going-concern language signals financing and covenant pressure"),
                ("delisting notice", 20, "Delisting notices threaten liquidity and index ownership"),
                ("market manipulation", 22, "Manipulation allegations can impair trading and financing"),
                ("insider trading", 20, "Insider-trading cases can implicate governance and controls"),
                ("class action", 12, "Securities class actions add legal cost and settlement risk"),
                ("revenue recognition", 18, "Revenue-recognition issues often precede restatements and credibility loss"),
                ("disgorgement", 16, "Disgorgement language usually accompanies charged enforcement resolutions"),
                ("fcpa", 20, "FCPA matters imply multi-year investigations and governance remediation"),
                ("foreign corrupt practices", 20, "FCPA-style matters imply multi-year investigations and fines"),
                ("deferred prosecution", 14, "Deferred-prosecution agreements still embed oversight and conduct risk"),
                ("trading halt", 16, "Trading halts often coincide with material disclosure uncertainty"),
                ("delisting", 18, "Delisting threats impair liquidity and institutional ownership"),
                ("pcaob", 14, "PCAOB scrutiny often implies auditor or controls exposure"),
                ("audit committee", 12, "Audit-committee-led reviews can widen into restatement risk"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)

            positive_offsets = [
                ("without admitting or denying", 10, "Settle-without-admitting language can reduce narrative severity vs charged fraud"),
                ("dismissed", 16, "Dismissal language lowers active enforcement overhang"),
                ("no findings of fraud", 18, "No-fraud findings reduce worst-case accounting narrative"),
                ("terminated investigation", 14, "Closed investigations reduce open regulatory tail risk"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)

        elif event_category == "supply_chain_disruption":
            weighted_markers = [
                ("supply chain disruption", 22, "Direct supply-chain disruption language signals throughput risk"),
                ("production halt", 24, "Production halts directly pressure near-term output"),
                ("plant shutdown", 22, "Plant shutdowns constrain capacity and revenue timing"),
                ("factory fire", 22, "Factory or plant incidents can erase near-term production"),
                ("force majeure", 20, "Force majeure implies contractual and delivery uncertainty"),
                ("supplier bankruptcy", 24, "Supplier failure can strand inventory and revenue"),
                ("supplier failure", 22, "Supplier failure can strand inventory and revenue"),
                ("chip shortage", 18, "Input shortages can constrain shipments and margins"),
                ("semiconductor shortage", 18, "Semiconductor shortages can delay production"),
                ("port congestion", 16, "Port and logistics congestion delays fulfillment"),
                ("port closure", 20, "Port closures can halt inbound and outbound flows"),
                ("logistics disruption", 18, "Logistics disruption increases working capital and delays"),
                ("labor strike", 14, "Strikes can halt plants or transport lanes"),
                ("strike at", 14, "Strike language at facilities can stop production or shipping"),
                ("freight rates", 12, "Freight shocks can compress margins"),
                ("inventory shortage", 14, "Inventory shortages imply demand or production mismatch"),
                ("backlog", 12, "Order backlog language signals capacity constraints"),
                ("container shortage", 16, "Container shortages constrain export/import timing"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)
            positive_offsets = [
                ("resumes production", 12, "Production restart language reduces acute disruption severity"),
                ("resumed operations", 12, "Operational normalization lowers disruption tail risk"),
                ("alleviates shortage", 10, "Alleviated shortage language can ease margin pressure narrative"),
                ("easing supply", 10, "Easing supply language can reduce bottleneck narrative"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "financial_distress":
            weighted_markers = [
                ("chapter 11", 34, "Chapter 11 filing signals acute balance-sheet stress"),
                ("chapter 7", 32, "Chapter 7 language implies liquidation risk"),
                ("bankruptcy", 30, "Bankruptcy language implies severe solvency pressure"),
                ("going concern", 26, "Going-concern disclosure is a high-signal distress marker"),
                ("payment default", 24, "Payment default indicates immediate creditor pressure"),
                ("missed interest payment", 22, "Missed coupon language elevates restructuring probability"),
                ("covenant breach", 20, "Covenant breaches often trigger lender renegotiation risk"),
                ("covenant default", 22, "Covenant default indicates contract breach with debt holders"),
                ("forbearance", 18, "Forbearance agreements imply near-term refinancing stress"),
                ("restructuring support agreement", 24, "RSA language usually precedes formal restructuring path"),
                ("liquidity crisis", 22, "Liquidity stress can force fire-sale financing decisions"),
                ("insolvency", 24, "Insolvency references imply extreme downside scenarios"),
                ("credit rating downgrade", 14, "Downgrades can raise refinancing costs and covenant pressure"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)
            positive_offsets = [
                ("refinancing completed", 14, "Completed refinancing can ease near-term maturity pressure"),
                ("debt repaid", 12, "Debt repayment language reduces immediate distress pressure"),
                ("liquidity improved", 10, "Liquidity improvement reduces near-term default risk"),
                ("covenant waiver", 8, "Waivers can buy time versus technical default outcomes"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "dilutive_financing":
            weighted_markers = [
                ("secondary offering", 18, "Secondary offerings can pressure share supply and valuation"),
                ("at-the-market", 20, "ATM programs can create ongoing dilution overhang"),
                ("atm offering", 20, "ATM programs can create ongoing dilution overhang"),
                ("registered direct offering", 20, "Registered direct deals often price at discount"),
                ("private placement", 18, "Private placements can dilute existing holders"),
                ("convertible notes", 20, "Convertible issuance embeds future dilution risk"),
                ("convertible preferred", 18, "Convertibles can cap upside and add share overhang"),
                ("warrant issuance", 18, "Warrants add contingent dilution"),
                ("equity line", 18, "Equity lines can increase persistent issuance pressure"),
                ("priced at discount", 22, "Discounted offerings usually imply stressed financing terms"),
                ("dilution", 16, "Explicit dilution language is negative for existing shareholders"),
                ("capital raise", 14, "Capital raises can reflect funding gap and dilution needs"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)
            positive_offsets = [
                ("oversubscribed", 8, "Oversubscription can soften signaling impact of financing"),
                ("minimal dilution", 10, "Explicit low-dilution language reduces downside narrative"),
                ("non-dilutive tranche", 12, "Non-dilutive capital components reduce equity pressure"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "ma_corporate_action":
            weighted_markers = [
                ("hostile bid", 14, "Hostile processes can raise execution and legal uncertainty"),
                ("competing bid", 12, "Competing bids increase deal path uncertainty and volatility"),
                ("deal termination", 20, "Terminated transactions often drive repricing risk"),
                ("deal break", 20, "Broken deals remove expected premium and can trigger downside"),
                ("antitrust challenge", 16, "Antitrust challenges increase closing risk"),
                ("doj sues to block", 22, "DOJ action materially elevates transaction failure risk"),
                ("ftc sues to block", 22, "FTC action materially elevates transaction failure risk"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)
            positive_offsets = [
                ("definitive merger agreement", 8, "Definitive agreement reduces uncertainty vs rumor"),
                ("transaction closes", 14, "Closed transactions reduce execution uncertainty"),
                ("shareholder approval", 8, "Shareholder approval de-risks one major close condition"),
                ("all-cash deal", 6, "All-cash terms can lower financing uncertainty"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "leadership_scandal":
            weighted_markers = [
                ("terminated for cause", 24, "For-cause terminations imply severe governance breakdown"),
                ("executive misconduct", 20, "Misconduct allegations can damage trust and execution"),
                ("board investigation", 18, "Board probes imply unresolved governance risk"),
                ("ethics probe", 16, "Ethics probes can widen legal and reputational overhang"),
                ("whistleblower complaint", 16, "Whistleblower claims often trigger prolonged investigations"),
                ("ceo resigns", 14, "Unplanned CEO turnover creates strategy uncertainty"),
                ("cfo resigns", 14, "CFO turnover can weaken reporting confidence"),
                ("compliance failure", 16, "Compliance breakdowns can trigger fines and remediation spend"),
                ("conflict of interest", 14, "Conflict disclosures can pressure board credibility"),
                ("succession uncertainty", 12, "Succession uncertainty can impair execution confidence"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)
            positive_offsets = [
                ("interim ceo appointed", 8, "Interim leadership can reduce immediate uncertainty"),
                ("independent review completed", 10, "Completed review narrows open-ended governance overhang"),
                ("no wrongdoing found", 14, "No-wrongdoing conclusions reduce scandal tail risk"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)
        elif event_category == "positive_earnings_catalyst":
            weighted_markers = [
                ("margin compression", 10, "Margin pressure can offset headline catalyst strength"),
                ("below expectations", 14, "Below-consensus details can reverse positive setup"),
                ("withdraws guidance", 20, "Guidance withdrawal increases uncertainty despite headline beats"),
            ]
            for marker, weight, reason in weighted_markers:
                if marker in content:
                    score += weight
                    reasons.append(reason)
            positive_offsets = [
                ("raised guidance", 18, "Raised guidance reduces near-term distress risk"),
                ("guidance increased", 18, "Guidance increases reduce downside expectations"),
                ("beat estimates", 12, "Beats can improve confidence in near-term fundamentals"),
                ("record revenue", 12, "Record revenue lowers immediate distress narrative"),
                ("margin expansion", 10, "Margin expansion indicates improving operating leverage"),
                ("above consensus", 10, "Above-consensus prints can de-risk near-term expectations"),
            ]
            for marker, weight, reason in positive_offsets:
                if marker in content:
                    score -= weight
                    reasons.append(reason)

        score = max(0, min(100, score))
        if score >= 70:
            likelihood = "HIGH"
        elif score >= 45:
            likelihood = "MEDIUM"
        else:
            likelihood = "LOW"

        return {
            "score": score,
            "likelihood": likelihood,
            "reasons": reasons[:4],
        }

    @staticmethod
    def _depth_categories() -> List[str]:
        return [
            "cybersecurity",
            "clinical_regulatory_binary",
            "product_safety_recall",
            "fraud_accounting_enforcement",
            "supply_chain_disruption",
            "financial_distress",
            "dilutive_financing",
            "ma_corporate_action",
            "leadership_scandal",
            "positive_earnings_catalyst",
        ]

    def _active_event_categories(self) -> List[str]:
        """Return enabled event categories from settings (fallback to depth set)."""
        event_cfg = self.settings.get("event_categories", {})
        if not isinstance(event_cfg, dict):
            return self._depth_categories()
        enabled = [
            name
            for name, cfg in event_cfg.items()
            if isinstance(cfg, dict) and cfg.get("enabled", False)
        ]
        return enabled or self._depth_categories()

    def _event_distress_fields(self, event: Dict) -> tuple:
        """Return (likelihood, score_int) from explicit fields or legacy tags."""
        like = str(event.get("distress_likelihood", "")).upper().strip()
        score_raw = str(event.get("distress_score", "")).strip()

        if not like or not score_raw:
            subtype = str(event.get("event_subtype") or event.get("breach_type") or "")
            summary = str(event.get("summary") or "")
            import re as _re
            m = _re.search(r"\[Distress\s+(LOW|MEDIUM|HIGH)\s+(\d{1,3})/100\]", f"{subtype} {summary}", _re.IGNORECASE)
            if m:
                like = like or m.group(1).upper()
                score_raw = score_raw or m.group(2)

        try:
            score = int(score_raw)
        except ValueError:
            score = 0
        score = max(0, min(100, score))
        return like or "UNKNOWN", score

    def _distress_gate_min_score(self, event_category: str) -> int:
        """
        Minimum distress score required to create a watch for a category.

        Config shape:
        {
          "distress_model": {
            "min_score_for_watch_default": 35,
            "min_score_for_watch_by_category": {"clinical_regulatory_binary": 40}
          }
        }
        """
        cfg = self.settings.get("distress_model", {})
        by_category = cfg.get("min_score_for_watch_by_category", {})
        if isinstance(by_category, dict):
            value = by_category.get(event_category)
            if value is not None:
                try:
                    return max(0, min(100, int(value)))
                except (TypeError, ValueError):
                    pass

        default_value = cfg.get("min_score_for_watch_default", 0)
        try:
            return max(0, min(100, int(default_value)))
        except (TypeError, ValueError):
            return 0

    def _triage_thresholds(self) -> tuple:
        """Return (min_impact_score, min_distress_score) from triage config."""
        triage_cfg = self.settings.get("triage", {})
        try:
            min_impact = int(triage_cfg.get("min_impact_score_for_alert", 60))
        except (TypeError, ValueError):
            min_impact = 60
        try:
            min_distress = int(triage_cfg.get("min_distress_score_for_alert", 35))
        except (TypeError, ValueError):
            min_distress = 35
        return max(0, min(100, min_impact)), max(0, min(100, min_distress))

    def _signal_triage_thresholds(self) -> tuple:
        """
        Return (min_impact_score, min_distress_score) required before saving buy signals.

        Falls back to alert thresholds when explicit signal thresholds are not configured.
        """
        triage_cfg = self.settings.get("triage", {})
        alert_impact, alert_distress = self._triage_thresholds()
        try:
            min_impact = int(triage_cfg.get("min_impact_score_for_signal", alert_impact))
        except (TypeError, ValueError):
            min_impact = alert_impact
        try:
            min_distress = int(triage_cfg.get("min_distress_score_for_signal", alert_distress))
        except (TypeError, ValueError):
            min_distress = alert_distress
        return max(0, min(100, min_impact)), max(0, min(100, min_distress))

    def display_menu(self) -> None:
        """Display main menu"""
        print("\n" + "="*80)
        print("CATASTROPHE ANALYZER - Event & Stock Opportunity Detection")
        print("="*80)
        print("\n1. Run production-equivalent cycle once (detect + analyze + alerts)")
        print("2. Scan for events (interactive/manual)")
        print("3. Analyze recent events (interactive/manual)")
        print("4. Generate buy signals (interactive/manual)")
        print("5. View signal history")
        print("6. View event history")
        print("7. Database statistics")
        print("8. Settings & configuration")
        print("9. Manage triage alert state (ACK/SUPPRESS)")
        print("10. Exit\n")

    def run(self) -> None:
        """Run the application"""
        print("\n" + "="*80)
        print("CATASTROPHE ANALYZER - Starting")
        print("="*80)

        while True:
            self.display_menu()
            choice = input("Enter choice (1-10): ").strip()

            if choice == '1':
                self.run_production_cycle_once()
            elif choice == '2':
                self.scan_events()
            elif choice == '3':
                self.analyze_events()
            elif choice == '4':
                self.generate_signals()
            elif choice == '5':
                self.view_signals()
            elif choice == '6':
                self.view_events()
            elif choice == '7':
                self.show_statistics()
            elif choice == '8':
                self.settings_menu()
            elif choice == '9':
                self.manage_triage_alert_state()
            elif choice == '10':
                print("\nExiting Catastrophe Analyzer. Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")

    def run_production_cycle_once(self) -> None:
        """
        Run the exact production service-path cycle once, including alert side effects.
        """
        print("\n" + "-"*80)
        print("PRODUCTION-EQUIVALENT CYCLE (ONCE)")
        print("-"*80)

        alerts = AlertManager()
        run_service_loop(
            self,
            alerts,
            quiet=False,
            once=True,
            interval_minutes=None,
        )
        print("✓ Production-equivalent cycle completed.")

    def manage_triage_alert_state(self) -> None:
        """Manage triage sent-state rows (ACK/SUPPRESS/RESET)."""
        print("\n" + "-" * 80)
        print("TRIAGE ALERT STATE")
        print("-" * 80)

        state_input = input(
            "Filter state [NEW/SENT/ACKED/SUPPRESSED/all] (default=SENT): "
        ).strip().upper()
        if not state_input:
            state_input = "SENT"
        if state_input not in ("NEW", "SENT", "ACKED", "SUPPRESSED", "ALL"):
            print("Invalid state filter.")
            return

        state_filter = None if state_input == "ALL" else state_input
        rows = self.db.get_triage_events(alert_state=state_filter)
        if not rows:
            print("No triage rows match this filter.")
            return

        # Most recent first by last_seen_at
        rows = sorted(rows, key=lambda r: r.get("last_seen_at", ""), reverse=True)
        max_show = min(len(rows), 25)
        print(f"\nShowing {max_show} of {len(rows)} triage rows:")
        print("-" * 80)
        for i, row in enumerate(rows[:max_show], 1):
            print(
                f"{i:>2}. {row.get('ticker', ''):<8} "
                f"{row.get('event_category', ''):<28} "
                f"impact={row.get('impact_likelihood', '')}({row.get('impact_score', '')}) "
                f"distress={row.get('distress_likelihood', '')}({row.get('distress_score', '')}) "
                f"state={row.get('alert_state', '')}"
            )

        print("\nActions:")
        print("  1) ACK selected rows")
        print("  2) SUPPRESS selected rows")
        print("  3) RESET selected rows to NEW")
        print("  4) Back")
        action = input("Choose action (1-4): ").strip()
        if action == "4":
            return
        action_map = {"1": "ACKED", "2": "SUPPRESSED", "3": "NEW"}
        target_state = action_map.get(action)
        if not target_state:
            print("Invalid action.")
            return

        index_input = input(
            "Enter row numbers (comma-separated, e.g. 1,3,5): "
        ).strip()
        if not index_input:
            print("No rows selected.")
            return

        selected_indices = []
        for token in index_input.split(","):
            token = token.strip()
            if not token.isdigit():
                continue
            n = int(token)
            if 1 <= n <= max_show:
                selected_indices.append(n - 1)

        if not selected_indices:
            print("No valid row numbers selected.")
            return

        updated = 0
        for idx in selected_indices:
            event_key = rows[idx].get("event_key", "")
            if event_key and self.db.mark_triage_state(event_key, target_state):
                updated += 1

        print(f"Updated {updated} row(s) to state {target_state}.")

    def _parse_published_date(self, published: str, fallback_date: str) -> str:
        """Parse RSS published string into YYYY-MM-DD."""
        if not published or published == 'Unknown':
            return fallback_date

        try:
            # Handles RFC2822 timestamps like "Mon, 18 Mar 2026 11:00:00 GMT"
            dt = parsedate_to_datetime(published)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        try:
            # Handles ISO timestamps
            s = (published or '').replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return fallback_date

    def _classify_event_subtype_and_severity(
        self,
        title: str,
        summary: str,
        event_category: str = "cybersecurity",
    ) -> tuple:
        """Heuristic event subtype + severity. Used for persistence/alert context only."""
        content = f"{title} {summary}".lower()

        if event_category == "clinical_regulatory_binary":
            event_subtype = "Clinical/Regulatory Update"
            if "complete response letter" in content or "crl" in content:
                event_subtype = "FDA Complete Response Letter"
            elif "partial clinical hold" in content:
                event_subtype = "Partial Clinical Hold"
            elif "trial hold" in content or "clinical hold" in content:
                event_subtype = "Clinical Hold"
            elif "fda approval" in content or "approved by the fda" in content:
                event_subtype = "FDA Approval"
            elif "adcom" in content and any(marker in content for marker in ("negative vote", "against", "concern")):
                event_subtype = "AdCom Negative Vote"
            elif "phase 3" in content and any(
                marker in content for marker in ("failed", "fails", "missed", "did not meet")
            ):
                event_subtype = "Phase 3 Trial Failure"
            elif "phase 3" in content and any(
                marker in content for marker in ("met primary endpoint", "met endpoint", "positive data")
            ):
                event_subtype = "Phase 3 Trial Success"
            elif any(marker in content for marker in ("missed primary endpoint", "did not meet endpoint")):
                event_subtype = "Endpoint Miss"
            elif "fda" in content and any(marker in content for marker in ("reject", "rejected", "refuse to file")):
                event_subtype = "Regulatory Rejection"

            severity = "Medium"
            high_markers = [
                "complete response letter",
                "crl",
                "clinical hold",
                "trial hold",
                "rejected",
                "refuse to file",
                "phase 3 trial failure",
            ]
            if any(marker in content for marker in high_markers):
                severity = "High"
            return event_subtype, severity
        if event_category == "product_safety_recall":
            event_subtype = "Product Safety Event"
            if "class i recall" in content or "class 1 recall" in content:
                event_subtype = "Class I Recall"
            elif "grounding" in content:
                event_subtype = "Product Grounding"
            elif "recall" in content:
                event_subtype = "Product Recall"
            elif "do not use" in content or "stop sale" in content or "safety alert" in content:
                event_subtype = "Regulatory Safety Alert"
            elif "warning letter" in content:
                event_subtype = "Regulatory Warning Letter"
            elif "contamination" in content:
                event_subtype = "Contamination Incident"

            severity = "Medium"
            if any(
                marker in content
                for marker in (
                    "class i recall",
                    "class 1 recall",
                    "grounding",
                    "recall",
                    "do not use",
                    "stop sale",
                    "injury",
                    "fatality",
                    "contamination",
                    "production halt",
                )
            ):
                severity = "High"
            return event_subtype, severity

        if event_category == "fraud_accounting_enforcement":
            event_subtype = "Financial Reporting Event"
            if "wells notice" in content:
                event_subtype = "Wells Notice"
            elif any(
                marker in content
                for marker in (
                    "indictment",
                    "criminal charges",
                    "guilty plea",
                    "pleaded guilty",
                    "department of justice",
                    "u.s. attorney",
                    "wire fraud",
                )
            ):
                event_subtype = "DOJ Criminal Action"
            elif any(
                marker in content
                for marker in (
                    "sec charges",
                    "sec alleges",
                    "enforcement action",
                    "cease and desist",
                    "cease-and-desist",
                    "civil complaint",
                    "securities fraud",
                    "accounting fraud",
                    "market manipulation",
                    "insider trading",
                    "spoofing",
                )
            ):
                event_subtype = "SEC Enforcement Action"
            elif any(
                marker in content
                for marker in (
                    "restatement",
                    "restate financial",
                    "revised financial results",
                    "accounting irregularities",
                    "misstated financial",
                    "financial misstatement",
                )
            ):
                event_subtype = "Accounting Restatement"
            elif "material weakness" in content or "material weaknesses" in content:
                event_subtype = "Material Weakness Disclosure"
            elif "internal control" in content or "internal controls" in content:
                event_subtype = "Internal Control Failure"

            severity = "Medium"
            high_markers = [
                "indictment",
                "criminal charges",
                "guilty plea",
                "securities fraud",
                "accounting fraud",
                "restatement",
                "sec charges",
                "wells notice",
                "wire fraud",
                "going concern",
                "delisting notice",
            ]
            if any(marker in content for marker in high_markers):
                severity = "High"
            return event_subtype, severity

        if event_category == "supply_chain_disruption":
            event_subtype = "Supply Chain Event"
            if "port congestion" in content or "port closure" in content or "canal" in content:
                event_subtype = "Port/Logistics Disruption"
            elif "chip shortage" in content or "semiconductor shortage" in content or "component shortage" in content:
                event_subtype = "Component/Input Shortage"
            elif "factory fire" in content or "plant shutdown" in content or "production halt" in content:
                event_subtype = "Factory/Plant Disruption"
            elif "supplier bankruptcy" in content or "supplier failure" in content or "force majeure" in content:
                event_subtype = "Supplier/Contract Stress"
            elif "supply chain disruption" in content or "logistics disruption" in content:
                event_subtype = "Supply Chain Disruption"

            severity = "Medium"
            if any(
                marker in content
                for marker in (
                    "factory fire",
                    "plant shutdown",
                    "supplier bankruptcy",
                    "force majeure",
                    "production halt",
                    "port closure",
                    "supply chain disruption",
                )
            ):
                severity = "High"
            return event_subtype, severity

        if event_category == "financial_distress":
            event_subtype = "Financial Distress Event"
            if "chapter 11" in content or "bankruptcy protection" in content:
                event_subtype = "Chapter 11 Restructuring"
            elif "chapter 7" in content or "liquidation" in content:
                event_subtype = "Liquidation Risk"
            elif "going concern" in content:
                event_subtype = "Going Concern Warning"
            elif "payment default" in content or "missed interest payment" in content:
                event_subtype = "Debt Payment Default"
            elif "covenant breach" in content or "covenant default" in content:
                event_subtype = "Debt Covenant Breach"
            elif "forbearance" in content or "restructuring support agreement" in content:
                event_subtype = "Debt Restructuring Process"

            severity = "Medium"
            if any(
                marker in content
                for marker in (
                    "chapter 11",
                    "chapter 7",
                    "bankruptcy",
                    "going concern",
                    "payment default",
                    "insolvency",
                )
            ):
                severity = "High"
            return event_subtype, severity

        if event_category == "dilutive_financing":
            event_subtype = "Equity Financing Event"
            if "at-the-market" in content or "atm offering" in content:
                event_subtype = "ATM Equity Program"
            elif "registered direct offering" in content:
                event_subtype = "Registered Direct Offering"
            elif "private placement" in content or "pipe financing" in content:
                event_subtype = "Private Placement / PIPE"
            elif "convertible notes" in content or "convertible debt" in content or "convertible preferred" in content:
                event_subtype = "Convertible Financing"
            elif "secondary offering" in content or "follow-on offering" in content:
                event_subtype = "Secondary Equity Offering"
            elif "warrant issuance" in content or "pre-funded warrants" in content:
                event_subtype = "Warrant-Linked Financing"

            severity = "Medium"
            if any(
                marker in content
                for marker in (
                    "priced at discount",
                    "registered direct offering",
                    "convertible notes",
                    "dilution",
                    "equity line",
                )
            ):
                severity = "High"
            return event_subtype, severity

        if event_category == "ma_corporate_action":
            event_subtype = "M&A / Corporate Action"
            if "hostile bid" in content:
                event_subtype = "Hostile Bid"
            elif "competing bid" in content:
                event_subtype = "Competing Bid"
            elif "take-private" in content or "buyout" in content:
                event_subtype = "Take-Private Transaction"
            elif "tender offer" in content:
                event_subtype = "Tender Offer"
            elif "deal termination" in content or "deal break" in content:
                event_subtype = "Deal Termination"
            elif "merger agreement" in content or "acquisition" in content:
                event_subtype = "Merger/Acquisition Agreement"

            severity = "Medium"
            if any(
                marker in content
                for marker in (
                    "hostile bid",
                    "competing bid",
                    "deal termination",
                    "doj sues to block",
                    "ftc sues to block",
                )
            ):
                severity = "High"
            return event_subtype, severity

        if event_category == "leadership_scandal":
            event_subtype = "Leadership Governance Event"
            if "terminated for cause" in content:
                event_subtype = "For-Cause Executive Termination"
            elif "board investigation" in content or "special committee" in content:
                event_subtype = "Board/Special Committee Probe"
            elif "whistleblower complaint" in content:
                event_subtype = "Whistleblower Allegation"
            elif "ceo resigns" in content or "ceo steps down" in content:
                event_subtype = "CEO Departure"
            elif "cfo resigns" in content:
                event_subtype = "CFO Departure"
            elif "ethics probe" in content or "executive misconduct" in content:
                event_subtype = "Executive Misconduct Probe"

            severity = "Medium"
            if any(
                marker in content
                for marker in (
                    "terminated for cause",
                    "executive misconduct",
                    "board investigation",
                    "whistleblower complaint",
                    "compliance failure",
                )
            ):
                severity = "High"
            return event_subtype, severity

        if event_category == "positive_earnings_catalyst":
            event_subtype = "Positive Earnings Catalyst"
            if "raised guidance" in content or "raises guidance" in content or "guidance increased" in content:
                event_subtype = "Guidance Raise"
            elif "record revenue" in content or "record bookings" in content:
                event_subtype = "Record Topline Print"
            elif "beat estimates" in content or "above consensus" in content:
                event_subtype = "Consensus Beat"
            elif "margin expansion" in content:
                event_subtype = "Margin Expansion Catalyst"
            elif "positive preannouncement" in content:
                event_subtype = "Positive Preannouncement"

            severity = "Medium"
            if any(marker in content for marker in ("raised guidance", "record revenue", "positive preannouncement")):
                severity = "High"
            return event_subtype, severity

        event_subtype = "Security Incident"
        if "ransomware" in content:
            event_subtype = "Ransomware"
        elif "material cybersecurity incident" in content or "sec filing" in content or "8-k" in content:
            event_subtype = "Material Cyber Disclosure"
        elif "supply chain attack" in content:
            event_subtype = "Supply Chain Attack"
        elif "destructive malware" in content or "wiper" in content:
            event_subtype = "Destructive Malware"
        elif "service outage" in content or "operations disrupted" in content:
            event_subtype = "Major Service Outage"
        elif "unauthorized access" in content:
            event_subtype = "Unauthorized Access"
        elif "credential" in content or "credentials leaked" in content:
            event_subtype = "Credential Leak"
        elif "zero-day" in content or "zero day" in content:
            event_subtype = "Zero-Day Vulnerability"
        elif "exploit" in content:
            event_subtype = "Exploit"
        elif "vulnerability" in content:
            event_subtype = "Vulnerability"
        elif "data exposure" in content or "data breach" in content or "data leak" in content:
            event_subtype = "Data Breach"

        severity = "Medium"
        critical_markers = [
            "ransomware",
            "zero-day",
            "zero day",
            "critical",
            "exploit",
            "credential",
            "data breach",
            "data exposure",
            "material cybersecurity incident",
            "sec filing",
            "8-k",
            "supply chain attack",
            "destructive malware",
            "wiper",
            "operations disrupted",
        ]
        if any(marker in content for marker in critical_markers):
            severity = "High"
        return event_subtype, severity

    def _article_category_keywords(self, article: Dict) -> list:
        """Keywords for the article category, with cybersecurity fallback."""
        event_category = article.get("event_category", "cybersecurity")
        category_keywords = self.news_scraper.keywords_by_category.get(event_category, [])
        if category_keywords:
            return category_keywords
        return self.news_scraper.breach_keywords

    # Backward-compatible alias while callers migrate.
    def _classify_breach_type_and_severity(self, title: str, summary: str) -> tuple:
        return self._classify_event_subtype_and_severity(title, summary)

    def _select_canonical_entity(self, article: Dict) -> Optional[Dict]:
        """
        Choose the best (company, ticker) candidate for watch creation.

        This is where we reduce false positives by selecting the candidate that is
        closest (by string distance) to a breach keyword in the article text,
        and preferring US-listed-like tickers (no '.' in symbol).
        """
        candidates = article.get("mapped_entities", []) or []
        if not candidates:
            return None

        title = article.get("title", "") or ""
        summary = article.get("summary", "") or ""
        content_lower = f"{title} {summary}".lower()
        category_keywords = [k.lower() for k in self._article_category_keywords(article)]

        # Find candidate keyword positions once
        kw_positions = []
        for kw in category_keywords:
            pos = content_lower.find(kw)
            if pos != -1:
                kw_positions.append(pos)
        # If nothing found (shouldn't happen due to earlier filtering), fall back to keyword-less
        if not kw_positions:
            kw_positions = [0]

        best = None
        # (distance, us_preference, len(company)) - smaller is better
        best_tuple = None

        for c in candidates:
            company = c.get("company", "") or ""
            ticker = (c.get("ticker", "") or "").strip()
            validation_status = str(c.get("validation_status", "approved")).lower().strip()
            if not ticker or ticker == "UNKNOWN":
                continue
            if validation_status and validation_status != "approved":
                continue

            company_lower = company.lower()
            comp_pos = content_lower.find(company_lower)
            if comp_pos == -1:
                # If we can't find it in text, treat as far away.
                comp_pos = 10**9

            # Distance to nearest keyword occurrence
            distance = min(abs(comp_pos - p) for p in kw_positions)
            us_preference = 1 if "." not in ticker else 0
            # Prefer shorter company strings when distance/us_preference match.
            cand_tuple = (distance, -us_preference, len(company))
            if best_tuple is None or cand_tuple < best_tuple:
                best_tuple = cand_tuple
                best = {
                    "company": company,
                    "ticker": ticker,
                    "validation_status": c.get("validation_status", "approved"),
                    "validation_reason": c.get("validation_reason", ""),
                    "validation_confidence": c.get("validation_confidence", ""),
                    "validation_engine": c.get("validation_engine", "deterministic"),
                }

        return best

    def detect_new_events(self, quiet: bool = False) -> Dict:
        """
        Scan recent RSS items and create new event watch entries.

        Uses `scraping.hours_back` only for detection; once created, watches remain active
        for `breach_watch.max_days`.
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        hours_back = int(self.settings.get('scraping', {}).get('hours_back', 24))

        if quiet:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw_articles = self.news_scraper.scrape_all_sources()
        else:
            raw_articles = self.news_scraper.scrape_all_sources()

        if not raw_articles:
            return {
                "articles": 0,
                "watches_created": 0,
                "new_high_value_events": [],
            }

        recent_articles = self.news_scraper.filter_recent_articles(raw_articles, hours_back)
        entities = self.entity_extractor.batch_extract(recent_articles)

        times_pre_days = int(self.settings.get("price_series", {}).get("pre_days", 30))
        times_post_days = int(self.settings.get("price_series", {}).get("post_days", 30))

        created = 0
        skipped_low_distress = 0
        skipped_unapproved_validation = 0

        for article in entities:
            if not article.get("has_publicly_traded"):
                if article.get("mapped_candidates"):
                    skipped_unapproved_validation += 1
                continue

            canonical = self._select_canonical_entity(article)
            if not canonical:
                continue

            published = article.get("published", "Unknown")
            event_date = self._parse_published_date(published, fallback_date=today_str)
            event_category = article.get("event_category", "cybersecurity")

            title = article.get("title", "") or ""
            summary = article.get("summary", "") or ""
            event_subtype, severity = self._classify_event_subtype_and_severity(
                title=title,
                summary=summary,
                event_category=event_category,
            )
            distress = self._financial_distress_assessment(
                title=title,
                summary=summary,
                event_category=event_category,
            )
            distress_label = distress.get("likelihood", "LOW")
            distress_score = distress.get("score", 0)
            distress_gate = self._distress_gate_min_score(event_category)
            if distress_score < distress_gate:
                skipped_low_distress += 1
                continue

            triage_payload = {
                "title": title,
                "summary": summary,
                "event_category": event_category,
                "event_subtype": event_subtype,
                "distress_score": distress_score,
                "distress_likelihood": distress_label,
            }
            triage = self.impact_triage.evaluate(triage_payload)
            if self._severity_rank(distress_label) > self._severity_rank(severity):
                severity = distress_label.title()

            event_key = self.db.build_event_key(
                ticker=canonical["ticker"],
                event_date=event_date,
                event_category=event_category,
                source_url=article.get("link", ""),
                title=title,
            )
            triage_record = {
                "event_key": event_key,
                "ticker": canonical["ticker"],
                "company": canonical["company"],
                "event_date": event_date,
                "event_category": event_category,
                "event_subtype": event_subtype,
                "distress_score": distress_score,
                "distress_likelihood": distress_label,
                "impact_score": triage.get("impact_score", 0),
                "impact_likelihood": triage.get("impact_likelihood", "LOW"),
                "impact_summary": triage.get("impact_summary", ""),
                "triage_engine": triage.get("triage_engine", "deterministic"),
                "validation_status": canonical.get("validation_status", "approved"),
                "validation_reason": canonical.get("validation_reason", ""),
                "validation_confidence": canonical.get("validation_confidence", ""),
                "validation_engine": canonical.get("validation_engine", "deterministic"),
                "alert_state": "NEW",
                "url": article.get("link", ""),
                "title": title,
            }
            self.db.upsert_triage_event(triage_record)

            watch = {
                "ticker": canonical["ticker"],
                "company": canonical["company"],
                "event_date": event_date,
                "breach_date": event_date,  # Legacy compatibility for stream-B merge gap.
                "event_category": event_category,
                "event_subtype": event_subtype,
                "distress_likelihood": distress_label,
                "distress_score": distress_score,
                "source": article.get("source", ""),
                "url": article.get("link", ""),
                "watch_start_date": event_date,
                "last_checked_at": datetime.now().isoformat(),
                "status": "ACTIVE",
                "timeseries_saved": "No",
            }

            if self.db.add_watch_if_new(watch):
                created += 1

                # Persist event record (legacy add_breach API still used for compatibility).
                self.db.add_breach({
                    "date_found": event_date,
                    "event_date": event_date,
                    "event_category": event_category,
                    "company": canonical["company"],
                    "ticker": canonical["ticker"],
                    "event_subtype": event_subtype,
                    "distress_likelihood": distress_label,
                    "distress_score": distress_score,
                    "breach_type": event_subtype,
                    "severity": severity,
                    "source": watch.get("source", ""),
                    "url": watch.get("url", ""),
                    "summary": (summary or "")[:500],
                })

                # Persist price timeseries for the watch (first deliverable)
                series_rows = self.stock_analyzer.get_event_price_series(
                    ticker=canonical["ticker"],
                    event_date=event_date,
                    pre_days=times_pre_days,
                    post_days=times_post_days,
                )
                if series_rows:
                    self.db.add_price_timeseries(series_rows)
                    self.db.mark_timeseries_saved(canonical["ticker"], event_date)
            else:
                # Keep watchlist company metadata aligned with latest canonical selection.
                self.db.update_watch_metadata(
                    ticker=canonical["ticker"],
                    breach_date=event_date,
                    company=canonical["company"],
                    source=article.get("source", ""),
                    url=article.get("link", ""),
                )

        return {
            "articles": len(recent_articles),
            "watches_created": created,
            "skipped_low_distress": skipped_low_distress,
            "skipped_unapproved_validation": skipped_unapproved_validation,
            "new_high_value_events": self.db.get_triage_events(
                alert_state="NEW",
                min_impact_score=self._triage_thresholds()[0],
                min_distress_score=self._triage_thresholds()[1],
            ),
        }

    # Backward-compatible alias while monitor/callers migrate.
    def detect_new_breaches(self, quiet: bool = False) -> Dict:
        return self.detect_new_events(quiet=quiet)

    def update_watches_and_generate_signals(self, quiet: bool = False) -> Dict:
        """
        For each ACTIVE watch in the last `max_days`, analyze stock movement and create buy signals.
        """
        watch_cfg = self.settings.get("event_watch", self.settings.get("breach_watch", {}))
        max_days = int(watch_cfg.get("max_days", 7))

        active_watches = self.db.get_active_watches(max_days=max_days)
        if not active_watches:
            return {
                "watches_checked": 0,
                "signals_generated": 0,
                "signals_generated_raw": 0,
                "signals_after_confidence_gate": 0,
                "signals_after_triage_gate": 0,
                "signals_saved": 0,
                "new_signals": [],
            }

        # Don't spam with repeated signals
        existing_signals = self.db.get_signals()
        existing_signal_keys = {
            (
                s.get("ticker", ""),
                s.get("event_date", s.get("breach_date", "")),
                s.get("event_category", ""),
                s.get("signal_type", ""),
            )
            for s in existing_signals
        }

        existing_analyses = self.db.get_analysis_history()
        existing_analysis_keys = {
            (
                a.get("ticker", ""),
                a.get("event_date", a.get("breach_date", "")),
                a.get("event_category", ""),
            )
            for a in existing_analyses
        }

        analyses_requests = []
        watches_to_check = []
        watch_context_by_key = {}
        for w in active_watches:
            status = (w.get("status") or "").upper()
            if status == "SIGNAL_CREATED":
                # Already signaled; still update timestamp but don't re-signal.
                self.db.mark_watch_last_checked(w.get("ticker", ""), w.get("event_date", w.get("breach_date", "")))
                continue

            ticker = w.get("ticker", "")
            event_date = w.get("event_date", w.get("breach_date", ""))
            event_category = w.get("event_category", "")
            if not ticker or not event_date:
                continue

            watches_to_check.append(w)
            watch_context_by_key[(ticker, event_date, event_category)] = {
                "company": w.get("company", ""),
                "event_subtype": w.get("event_subtype", ""),
                "distress_score": w.get("distress_score", ""),
                "url": w.get("url", ""),
                "source": w.get("source", ""),
            }
            analyses_requests.append(
                {
                    "ticker": ticker,
                    "company": w.get("company", ""),
                    "event_date": event_date,
                    "breach_date": event_date,
                    "event_category": event_category,
                }
            )

        if not analyses_requests:
            return {
                "watches_checked": len(watches_to_check),
                "signals_generated": 0,
                "signals_generated_raw": 0,
                "signals_after_confidence_gate": 0,
                "signals_after_triage_gate": 0,
                "signals_saved": 0,
                "new_signals": [],
            }

        analyses = self.stock_analyzer.batch_analyze(analyses_requests)
        signals = self.signal_generator.generate_signals_batch(analyses)
        ranked_signals = self.signal_generator.rank_signals(signals)
        triage_context_by_key = {}
        watch_keys = set(watch_context_by_key.keys())
        for triage in self.db.get_triage_events_for_keys(list(watch_keys)):
            key = (
                triage.get("ticker", ""),
                triage.get("event_date", ""),
                triage.get("event_category", ""),
            )
            if key not in watch_keys:
                continue
            triage_context_by_key[key] = {
                "title": triage.get("title", ""),
                "impact_summary": triage.get("impact_summary", ""),
                "event_subtype": triage.get("event_subtype", ""),
                "url": triage.get("url", ""),
                "impact_score": triage.get("impact_score", ""),
                "distress_score": triage.get("distress_score", ""),
            }

        min_conf = self.signal_generator.signal_config.get('min_confidence_for_signal', 0.4)
        if isinstance(min_conf, (int, float)):
            ranked_signals = self.signal_generator.filter_signals(ranked_signals, min_confidence=float(min_conf))
        signals_after_confidence_gate = len(ranked_signals)

        def _score_to_int(value: object) -> int:
            try:
                raw = str(value).strip()
                if raw == "":
                    return 0
                return max(0, min(100, int(float(raw))))
            except ValueError:
                return 0

        saved_signals = 0
        signals_after_triage_gate = 0
        new_signals = []

        # Save analysis metrics
        for analysis in analyses:
            a_key = (
                analysis.get("ticker", ""),
                analysis.get("event_date", analysis.get("breach_date", "")),
                analysis.get("event_category", ""),
            )
            if a_key in existing_analysis_keys or "error" in analysis:
                continue
            if self.db.add_analysis(analysis):
                existing_analysis_keys.add(a_key)

        # Save signals + mark watch
        signal_min_impact, signal_min_distress = self._signal_triage_thresholds()
        for signal in ranked_signals:
            s_key = (
                signal.get("ticker", ""),
                signal.get("event_date", signal.get("breach_date", "")),
                signal.get("event_category", ""),
                signal.get("signal_type", ""),
            )
            event_key = (
                signal.get("ticker", ""),
                signal.get("event_date", signal.get("breach_date", "")),
                signal.get("event_category", ""),
            )
            watch_ctx = watch_context_by_key.get(event_key, {})
            triage_ctx = triage_context_by_key.get(event_key, {})
            if watch_ctx:
                signal.setdefault("company", watch_ctx.get("company", ""))
                signal.setdefault("event_subtype", watch_ctx.get("event_subtype", ""))
                signal.setdefault("url", watch_ctx.get("url", ""))
            if triage_ctx:
                signal.setdefault("event_subtype", triage_ctx.get("event_subtype", ""))
                signal.setdefault("issue_summary", triage_ctx.get("impact_summary", ""))
                signal.setdefault("title", triage_ctx.get("title", ""))
                if not signal.get("url"):
                    signal["url"] = triage_ctx.get("url", "")

            # Keep signal gating resilient when triage rows are missing for an existing watch key.
            # Prefer explicit triage scores, then watch distress + signal confidence proxies.
            impact_score = max(
                _score_to_int(triage_ctx.get("impact_score", "")),
                _score_to_int(signal.get("impact_score", "")),
                _score_to_int(signal.get("confidence", "")),
            )
            distress_score = max(
                _score_to_int(triage_ctx.get("distress_score", "")),
                _score_to_int(signal.get("distress_score", "")),
                _score_to_int(watch_ctx.get("distress_score", "")),
            )
            if impact_score < signal_min_impact or distress_score < signal_min_distress:
                continue
            signals_after_triage_gate += 1
            if s_key in existing_signal_keys:
                continue
            if self.db.add_signal(signal):
                saved_signals += 1
                existing_signal_keys.add(s_key)
                new_signals.append(signal)
                self.db.mark_watch_signal_created(
                    signal.get("ticker", ""),
                    signal.get("event_date", signal.get("breach_date", "")),
                )

        # Update watch timestamps for those we checked
        for w in watches_to_check:
            self.db.mark_watch_last_checked(
                w.get("ticker", ""),
                w.get("event_date", w.get("breach_date", "")),
            )

        # Expire watches that are now out of window
        # (Keep this lightweight; full scan is fine for CSV sizes in this MVP.)
        now = datetime.now()
        for w in active_watches:
            try:
                bd = datetime.strptime(w.get("event_date", w.get("breach_date", "")), "%Y-%m-%d")
                if (now - bd).days > max_days:
                    self.db.mark_watch_expired(
                        w.get("ticker", ""),
                        w.get("event_date", w.get("breach_date", "")),
                    )
            except ValueError:
                continue

        return {
            "watches_checked": len(watches_to_check),
            "signals_generated": signals_after_triage_gate,
            "signals_generated_raw": len(signals),
            "signals_after_confidence_gate": signals_after_confidence_gate,
            "signals_after_triage_gate": signals_after_triage_gate,
            "signals_saved": saved_signals,
            "new_signals": new_signals,
        }

    def run_one_cycle(self, quiet: bool = False) -> Dict:
        """
        Run a single automatic cycle:
        1) scan for new events (create watch entries)
        2) update active watches and generate signals
        """
        detect_summary = self.detect_new_events(quiet=quiet)
        update_summary = self.update_watches_and_generate_signals(quiet=quiet)

        return {
            "articles": detect_summary.get("articles", 0),
            "watches_created": detect_summary.get("watches_created", 0),
            "skipped_low_distress": detect_summary.get("skipped_low_distress", 0),
            "new_high_value_events": detect_summary.get("new_high_value_events", []),
            "watches_checked": update_summary.get("watches_checked", 0),
            "signals_generated": update_summary.get("signals_generated", 0),
            "signals_generated_raw": update_summary.get("signals_generated_raw", 0),
            "signals_after_confidence_gate": update_summary.get("signals_after_confidence_gate", 0),
            "signals_after_triage_gate": update_summary.get("signals_after_triage_gate", 0),
            "signals_saved": update_summary.get("signals_saved", 0),
            "new_signals": update_summary.get("new_signals", []),
        }

    def scan_events(self) -> None:
        """Scan news sources for events"""
        print("\n" + "-"*80)
        print("SCANNING NEWS SOURCES")
        print("-"*80)

        # Scrape all sources
        self.current_articles = self.news_scraper.scrape_all_sources()

        if self.current_articles:
            print(f"\n✓ Found {len(self.current_articles)} event-related articles")

            # Entity pass so the scan shows public tickers + other mentions (same data reused if you continue)
            print("\nExtracting company names from headlines…")
            self.current_entities = self.entity_extractor.batch_extract(self.current_articles)
            self.entity_extractor.display_scan_preview(self.current_entities, max_articles=15)

            response = input("\nProceed to full analysis (detailed report + optional stock work)? (y/n): ").strip().lower()
            if response == 'y':
                self.analyze_events()
        else:
            print("\n✗ No event articles found in this scan")

    def analyze_events(self) -> None:
        """Extract entities and analyze stocks"""
        print("\n" + "-"*80)
        print("ANALYZING EVENTS")
        print("-"*80)

        if not self.current_articles:
            print("No articles to analyze. Please scan news sources first.")
            return

        print(f"\nProcessing {len(self.current_articles)} articles...")

        # Reuse extraction from scan when it matches this article set; otherwise refresh
        def _article_fingerprint(a: Dict) -> str:
            return (a.get("link") or "") + "|" + (a.get("title") or "")

        need_extract = (
            not self.current_entities
            or len(self.current_entities) != len(self.current_articles)
            or _article_fingerprint(self.current_articles[0])
            != _article_fingerprint(self.current_entities[0])
        )
        if need_extract:
            self.current_entities = self.entity_extractor.batch_extract(self.current_articles)
        self.entity_extractor.display_extraction_results(self.current_entities)

        # Articles with at least one US-listed ticker (per entity_extraction rules)
        publicly_traded = [e for e in self.current_entities if e.get('has_publicly_traded')]

        if publicly_traded:
            print(f"\n✓ Found {len(publicly_traded)} articles with US-listed tickers")

            # Build event-aligned analysis requests (parity with service path).
            unique_requests = {}
            for entity in publicly_traded:
                canonical = self._select_canonical_entity(entity)
                if not canonical:
                    continue
                published = entity.get("published", "Unknown")
                event_date = self._parse_published_date(
                    published,
                    fallback_date=datetime.now().strftime('%Y-%m-%d'),
                )
                event_category = entity.get("event_category", "cybersecurity")
                key = (canonical["ticker"], event_date, event_category)
                unique_requests[key] = {
                    "company": canonical["company"],
                    "ticker": canonical["ticker"],
                    "event_date": event_date,
                    "event_category": event_category,
                }

            print(f"✓ Unique ticker-event rows to analyze: {len(unique_requests)}")

            # Ask to proceed with analysis
            response = input("\nAnalyze stock impact for these companies? (y/n): ").strip().lower()
            if response == 'y':
                # Analyze stock impact
                print("\nAnalyzing stock prices...")
                companies_to_analyze = list(unique_requests.values())
                self.current_analyses = self.stock_analyzer.batch_analyze(
                    companies_to_analyze,
                )

                self.stock_analyzer.display_analysis(self.current_analyses)

                # Ask to generate signals
                response = input("\nGenerate trading signals? (y/n): ").strip().lower()
                if response == 'y':
                    self.generate_signals()
        else:
            print("\n✗ No US-listed tickers found in these articles (see scan preview for other mentions)")

    def generate_signals(self) -> None:
        """Generate trading signals from analysis"""
        print("\n" + "-"*80)
        print("GENERATING BUY SIGNALS")
        print("-"*80)

        if not self.current_analyses:
            print("No analyses available. Please analyze events first.")
            return

        print(f"\nGenerating signals from {len(self.current_analyses)} analyses...")

        # Generate signals
        self.current_signals = self.signal_generator.generate_signals_batch(self.current_analyses)

        if self.current_signals:
            # Rank by quality
            ranked_signals = self.signal_generator.rank_signals(self.current_signals)
            min_conf = self.signal_generator.signal_config.get("min_confidence_for_signal", 0.5)
            if isinstance(min_conf, (int, float)):
                ranked_signals = self.signal_generator.filter_signals(
                    ranked_signals,
                    min_confidence=float(min_conf),
                )

            print(f"\n✓ Generated {len(ranked_signals)} buy signals")
            self.signal_generator.display_signals(ranked_signals, detailed=True)

            # Ask to save signals
            response = input("\nSave signals to database? (y/n): ").strip().lower()
            if response == 'y':
                saved = 0
                for signal in ranked_signals:
                    if self.db.add_signal(signal):
                        saved += 1

                print(f"✓ Saved {saved} signals to database")

                # Ask to save analyses too
                response = input("Save analyses to database? (y/n): ").strip().lower()
                if response == 'y':
                    saved = 0
                    for analysis in self.current_analyses:
                        if self.db.add_analysis(analysis):
                            saved += 1

                    print(f"✓ Saved {saved} analyses to database")
        else:
            print("\n✗ No trading signals generated from these analyses")
            print("   (Stock prices may not meet buy criteria)")

    def view_signals(self) -> None:
        """View trading signal history"""
        print("\n" + "-"*80)
        print("TRADING SIGNAL HISTORY")
        print("-"*80)

        signals = self.db.get_signals()

        if not signals:
            print("No signals in database yet")
            return

        # Group by confidence
        high_conf = [s for s in signals if s.get('confidence_level') == 'HIGH']
        med_conf = [s for s in signals if s.get('confidence_level') == 'MEDIUM']
        low_conf = [s for s in signals if s.get('confidence_level') == 'LOW']

        print(f"\nTotal signals: {len(signals)}")
        print(f"  HIGH confidence:   {len(high_conf)}")
        print(f"  MEDIUM confidence: {len(med_conf)}")
        print(f"  LOW confidence:    {len(low_conf)}")

        # Show recent signals
        print("\nMost recent signals:")
        print("-"*40)

        for i, signal in enumerate(signals[-10:], 1):
            status = "✓ Executed" if signal.get('executed') == 'Yes' else "⏳ Pending"
            print(f"\n{i}. {signal.get('ticker')} - {status}")
            print(f"   Confidence:  {signal.get('confidence_level')} ({signal.get('confidence_score')}/100)")
            print(f"   Entry:       ${float(signal.get('entry_price', 0)):.2f}")
            print(f"   Stop Loss:   ${float(signal.get('stop_loss', 0)):.2f}")
            print(f"   Target:      ${float(signal.get('target_price', 0)):.2f}")
            print(f"   Signal Date: {signal.get('signal_date', 'Unknown')[:10]}")

    def view_events(self) -> None:
        """View event history"""
        print("\n" + "-"*80)
        print("EVENT HISTORY")
        print("-"*80)

        breaches = self.db.get_breaches()

        if not breaches:
            print("No events in database yet")
            return

        depth_categories = self._depth_categories()
        category_choice = input(
            f"Filter category [all/{'/'.join(depth_categories)}] (default=all): "
        ).strip().lower()
        if category_choice in depth_categories:
            breaches = [b for b in breaches if b.get("event_category", "").lower() == category_choice]

        distress_choice = input("Show only high distress events? (y/n, default=n): ").strip().lower()
        if distress_choice == "y":
            filtered = []
            for b in breaches:
                likelihood, score = self._event_distress_fields(b)
                if likelihood == "HIGH" or score >= 70:
                    filtered.append(b)
            breaches = filtered

        if not breaches:
            print("No events match current filters.")
            return

        # Group by severity
        severity_counts = {}
        for breach in breaches:
            sev = breach.get('severity', 'Unknown')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        print(f"\nTotal events: {len(breaches)}")
        for sev, count in severity_counts.items():
            print(f"  {sev}: {count}")

        by_category = {}
        for b in breaches:
            cat = b.get("event_category", "Unknown")
            by_category[cat] = by_category.get(cat, 0) + 1
        print("\nBy category:")
        for cat, count in by_category.items():
            print(f"  {cat}: {count}")

        # Show recent breaches
        print("\nMost recent events:")
        print("-"*40)

        for i, breach in enumerate(breaches[-10:], 1):
            distress_like, distress_score = self._event_distress_fields(breach)
            print(f"\n{i}. {breach.get('company')} ({breach.get('ticker')})")
            print(f"   Date:     {breach.get('date_found', 'Unknown')}")
            print(f"   Type:     {breach.get('breach_type', 'Unknown')}")
            print(f"   Category: {breach.get('event_category', 'Unknown')}")
            print(f"   Severity: {breach.get('severity', 'Unknown')}")
            print(f"   Distress: {distress_like} ({distress_score}/100)")
            print(f"   Source:   {breach.get('source', 'Unknown')}")

    # Backward-compatible aliases for existing call sites.
    def scan_breaches(self) -> None:
        self.scan_events()

    def analyze_breaches(self) -> None:
        self.analyze_events()

    def view_breaches(self) -> None:
        self.view_events()

    def show_statistics(self) -> None:
        """Display database statistics"""
        print("\n" + "-"*80)
        print("DATABASE STATISTICS")
        print("-"*80)

        self.db.display_statistics()
        self.db.display_category_yield_dashboard(
            days=30,
            categories=self._active_event_categories(),
        )

    def settings_menu(self) -> None:
        """Settings menu"""
        print("\n" + "-"*80)
        print("SETTINGS & CONFIGURATION")
        print("-"*80)
        print("\n1. View configuration")
        print("2. Export data to JSON")
        print("3. Reset database")
        print("4. Back to main menu\n")

        choice = input("Enter choice (1-4): ").strip()

        if choice == '1':
            self.view_configuration()
        elif choice == '2':
            filename = input("Enter filename (default: breach_analysis.json): ").strip()
            if not filename:
                filename = "breach_analysis.json"
            self.db.export_to_json(filename)
        elif choice == '3':
            response = input("WARNING: This will delete all data. Continue? (y/n): ").strip().lower()
            if response == 'y':
                self.reset_database()
        elif choice == '4':
            pass
        else:
            print("Invalid choice")

    def view_configuration(self) -> None:
        """View current configuration"""
        print("\n" + "="*60)
        print("Current Configuration")
        print("="*60)

        print("\nNews Sources:")
        for source, config in self.news_scraper.config.get('news_sources', {}).items():
            enabled = "✓ Enabled" if config.get('enabled') else "✗ Disabled"
            print(f"  • {source}: {enabled}")

        print("\nSignal Thresholds:")
        signals = self.signal_generator.signal_config
        print(f"  • RSI oversold threshold: {signals.get('rsi_oversold_threshold', 30)}")
        print(f"  • Price drop threshold: {signals.get('price_drop_threshold', 10)}%")
        print(f"  • Volume spike threshold: {signals.get('volume_spike_threshold', 1.5)}x")

        print("\nData Directory:")
        print(f"  • {self.db.data_dir}")

    def reset_database(self) -> None:
        """Reset all database files"""
        try:
            import os
            os.remove(self.db.breaches_file)
            os.remove(self.db.analysis_file)
            os.remove(self.db.signals_file)
            self.db._initialize_files()
            print("✓ Database reset successfully")
        except Exception as e:
            print(f"✗ Error resetting database: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--service",
        action="store_true",
        help="Run service loop parity mode (same runtime path as monitor.py).",
    )
    parser.add_argument("--interval-minutes", type=int, default=None, help="Override scan interval")
    parser.add_argument("--quiet", action="store_true", help="Reduce console output")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    # Keep relative-path behavior consistent with monitor.py runtime.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = CatastropheAnalyzerApp()
    if args.service or args.once or args.quiet or args.interval_minutes is not None:
        try:
            vmode = getattr(app.entity_extractor, "_validation_mode", "?")
        except Exception:
            vmode = "?"
        if not args.quiet:
            print(f"catastrophe-analyzer: entity validation mode={vmode}", flush=True)
        alerts = AlertManager()
        run_service_loop(
            app,
            alerts,
            quiet=args.quiet,
            once=args.once,
            interval_minutes=args.interval_minutes,
        )
        return

    app.run()


if __name__ == '__main__':
    main()
