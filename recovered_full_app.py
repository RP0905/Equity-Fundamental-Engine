from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
import json
import numpy as np
import pandas as pd
import requests
import os
import subprocess
from pathlib import Path
import re
import threading

# â”€â”€ Google Sheets services (primary data source) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from services.google_sheets_service import build_sheet_payload, search_master_index
from services.screener_csv_importer import import_screener_csv
from services.screener_local_service import (
    get_local_screener_status,
    run_local_screener,
    sync_screener_symbol,
    sync_screener_universe,
)

# â”€â”€ yfinance services (fallback) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from services.yf_services import get_stock_data
from analysis.technicals import get_technicals
from analysis.old_engine import get_old_data
from analysis.fundamentals import get_fundamentals

import yfinance as yf

app = Flask(__name__, static_folder=None)
CORS(app)
SPREADSHEET_METRIC_CACHE_PATH = Path(__file__).resolve().parent / "screener_metric_cache.jsonl"
YAHOO_METRIC_CACHE_PATH = Path(__file__).resolve().parent / "screener_yahoo_metric_cache.jsonl"
AI_AGENT_ROOT = Path(__file__).resolve().parent.parent / "Projects" / "Stock-Market-Agent"
AI_AGENT_BACKEND = "http://127.0.0.1:8000"
AI_AGENT_FRONTEND = "http://127.0.0.1:5173"
    app.run(debug=True)
RISKDESK_ROOT = Path(__file__).resolve().parent.parent / "Projects" / "riskdesk"
RISKDESK_BACKEND = "http://127.0.0.1:8001"
RISKDESK_FRONTEND = "http://127.0.0.1:5174"
RISKDESK_PROCESSES = []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def sanitize_json(value):
    """Recursively sanitize a JSON-serialisable structure, converting
    numpy types to plain Python types and filtering NaN / Inf."""
    if isinstance(value, dict):
        return {key: sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json(item) for item in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    if isinstance(value, float):
        if np.isnan(value) or np.isinf(value):
            return None
    return value


def _url_is_live(url, timeout=1.5):
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code < 500
    except Exception:
        return False


def _start_hidden_process(args, cwd, log_name, env=None, log_root=AI_AGENT_ROOT):
    log_path = log_root / log_name
    log_file = open(log_path, "a", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        args,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    AI_AGENT_PROCESSES.append((process, log_file))
    return process


def _start_ai_agent_servers():
    if not AI_AGENT_ROOT.exists():
        return False, f"AI project folder not found: {AI_AGENT_ROOT}"

    backend_dir = AI_AGENT_ROOT / "backend"
    frontend_dir = AI_AGENT_ROOT / "frontend"
    python_exe = AI_AGENT_ROOT / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        return False, f"AI agent virtual environment not found: {python_exe}"
    if not (frontend_dir / "package.json").exists():
        return False, f"AI agent frontend package.json not found: {frontend_dir}"

    backend_live = _url_is_live(f"{AI_AGENT_BACKEND}/docs")
    frontend_live = _url_is_live(AI_AGENT_FRONTEND)

    if not backend_live:
        _start_hidden_process(
            [str(python_exe), "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000"],
            backend_dir,
            "ai-agent-backend.log",
        )

    if not frontend_live:
        env = os.environ.copy()
        env["VITE_API_BASE"] = AI_AGENT_BACKEND
        _start_hidden_process(
            ["cmd.exe", "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
            frontend_dir,
            "ai-agent-frontend.log",
            env=env,
        )

    return True, "AI agent launch requested."


def _start_riskdesk_servers():
    if not RISKDESK_ROOT.exists():
        return False, f"RiskDesk project folder not found: {RISKDESK_ROOT}"

    backend_dir = RISKDESK_ROOT / "backend"
    frontend_dir = RISKDESK_ROOT
    if not (backend_dir / "app" / "main.py").exists():
        return False, f"RiskDesk backend was not found: {backend_dir}"
    if not (frontend_dir / "package.json").exists():
        return False, f"RiskDesk frontend package.json not found: {frontend_dir}"

    python_exe = (subprocess.check_output(["where", "python"], text=True).splitlines() or ["python"])[0].strip()

    backend_live = _url_is_live(f"{RISKDESK_BACKEND}/health")
    frontend_live = _url_is_live(RISKDESK_FRONTEND)

    if not backend_live:
        dependency_check = subprocess.run(
            [python_exe, "-c", "import fastapi, uvicorn, sqlalchemy, pydantic_settings, aiosqlite"],
            cwd=str(backend_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if dependency_check.returncode != 0:
            install_result = subprocess.run(
                [python_exe, "-m", "pip", "install", "-r", str(backend_dir / "requirements.txt")],
                cwd=str(backend_dir),
            )
            if install_result.returncode != 0:
                return False, "RiskDesk backend dependency installation failed."

        env = os.environ.copy()
        env["CORS_ORIGINS"] = f"http://localhost:5174,http://127.0.0.1:5174"
        process = _start_hidden_process(
            [python_exe, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
            backend_dir,
            "riskdesk-backend.log",
            env=env,
            log_root=RISKDESK_ROOT,
        )
        RISKDESK_PROCESSES.append(process)

    if not frontend_live:
        if not (frontend_dir / "node_modules").exists():
            install_result = subprocess.run(["cmd.exe", "/c", "npm", "install"], cwd=str(frontend_dir))
            if install_result.returncode != 0:
                return False, "RiskDesk frontend dependency installation failed."

        env = os.environ.copy()
        env["VITE_API_BASE"] = RISKDESK_BACKEND
        process = _start_hidden_process(
            ["cmd.exe", "/c", "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5174"],
            frontend_dir,
            "riskdesk-frontend.log",
            env=env,
            log_root=RISKDESK_ROOT,
        )
        RISKDESK_PROCESSES.append(process)

    return True, "RiskDesk launch requested."


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  BLOOMBERG-FRONTEND API  (Google Sheets primary)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/search", methods=["GET"])
def search():
    """Search the master index (Google Sheets)."""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    try:
        return jsonify(search_master_index(query))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/analyze", methods=["GET"])
def analyze():
    """Full analysis payload consumed by the Bloomberg-style frontend.

    Uses the Google Sheets service as the primary data source (via
    ``build_sheet_payload``) and falls back to yahoo-finance data when
    sheet data is unavailable.
    """
    query = (
        request.args.get("ticker", "").strip()
        or request.args.get("q", "").strip()
    )
    if not query:
        return jsonify({"error": "No company name provided"}), 400

    try:
        payload = build_sheet_payload(query, get_stock_data, get_technicals)
        if not payload:
            return jsonify({"error": "TICKER NOT FOUND IN INDEX"}), 404
        return jsonify(sanitize_json(payload))
    except Exception as exc:
        import traceback
        return jsonify({"error": str(exc), "trace": traceback.format_exc()}), 500


@app.route("/api/price-history", methods=["GET"])
def price_history():
    """OHLCV price history for the candlestick/line chart."""
    symbol = request.args.get("symbol", "").strip().upper()
    period = request.args.get("period", "1y")
    if not symbol:
        return jsonify({"error": "symbol required"}), 400

    # Map well-known indices to the correct yfinance ticker
    INDEX_MAP = {
        "NIFTY50": "^NSEI",
        "NIFTY": "^NSEI",
        "SENSEX": "^BSESN",
        "BANKNIFTY": "^NSEBANK",
    }
    yf_symbol = INDEX_MAP.get(symbol)
    if yf_symbol is None:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        yf_symbol = symbol

    try:
        stock = yf.Ticker(yf_symbol)
        df = stock.history(period=period, interval="1d")
        if df.empty:
            return jsonify({"error": "No data"}), 404
        records = []
        for _unused, row in df.iterrows():
            ts_seconds = int(row.name.timestamp()) if hasattr(row.name, "timestamp") else 0
            records.append({
                "time": ts_seconds,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return jsonify({"symbol": yf_symbol, "data": records})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/peers", methods=["GET"])
def peers():
    """Return peer comparison data for a given symbol."""
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"error": "symbol required"}), 400
    if not symbol.endswith(".NS"):
        symbol += ".NS"
    try:
        stock = yf.Ticker(symbol)
        info = stock.info or {}
        peers_raw = info.get("peerSymbols", []) or ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"]
        peer_list = []
        for ps in peers_raw[:8]:
            try:
                ps_str = ps.strip().upper()
                if not ps_str.endswith(".NS"):
                    ps_str += ".NS"
                pstock = yf.Ticker(ps_str)
                pinfo = pstock.info or {}
                peer_list.append({
                    "ticker": ps_str.replace(".NS", ""),
                    "price": pinfo.get("currentPrice") or pinfo.get("regularMarketPrice"),
                    "pe": pinfo.get("trailingPE"),
                    "mktCap": pinfo.get("marketCap"),
                })
            except Exception:
                continue
        return jsonify({"peers": peer_list})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/screener", methods=["POST"])
def screener():
    """Screen stocks using the Excel/Google-Sheets pipeline by default."""
    try:
        filters = request.get_json(silent=True) or {}
        print("=== Screener received filters ===")
        print(filters)
        
        use_local = filters.get("use_local_db", False)
        if use_local:
            print("[screener] Using LOCAL DB engine")
# MISSING LINE 321
# MISSING LINE 322
# MISSING LINE 323
# MISSING LINE 324
# MISSING LINE 325
# MISSING LINE 326
# MISSING LINE 327
# MISSING LINE 328
# MISSING LINE 329
# MISSING LINE 330
# MISSING LINE 331
# MISSING LINE 332
# MISSING LINE 333
# MISSING LINE 334
# MISSING LINE 335
# MISSING LINE 336
# MISSING LINE 337
# MISSING LINE 338
# MISSING LINE 339
# MISSING LINE 340
# MISSING LINE 341
# MISSING LINE 342
# MISSING LINE 343
# MISSING LINE 344
# MISSING LINE 345
# MISSING LINE 346
# MISSING LINE 347
# MISSING LINE 348
# MISSING LINE 349
# MISSING LINE 350
# MISSING LINE 351
# MISSING LINE 352
# MISSING LINE 353
# MISSING LINE 354
# MISSING LINE 355
# MISSING LINE 356
# MISSING LINE 357
# MISSING LINE 358
# MISSING LINE 359
# MISSING LINE 360
# MISSING LINE 361
# MISSING LINE 362
# MISSING LINE 363
# MISSING LINE 364
# MISSING LINE 365
# MISSING LINE 366
# MISSING LINE 367
# MISSING LINE 368
# MISSING LINE 369
# MISSING LINE 370
# MISSING LINE 371
# MISSING LINE 372
# MISSING LINE 373
# MISSING LINE 374
# MISSING LINE 375
# MISSING LINE 376
# MISSING LINE 377
# MISSING LINE 378
# MISSING LINE 379
# MISSING LINE 380
# MISSING LINE 381
# MISSING LINE 382
# MISSING LINE 383
# MISSING LINE 384
# MISSING LINE 385
# MISSING LINE 386
# MISSING LINE 387
# MISSING LINE 388
# MISSING LINE 389
# MISSING LINE 390
# MISSING LINE 391
# MISSING LINE 392
# MISSING LINE 393
# MISSING LINE 394
# MISSING LINE 395
# MISSING LINE 396
# MISSING LINE 397
# MISSING LINE 398
# MISSING LINE 399
# MISSING LINE 400
# MISSING LINE 401
# MISSING LINE 402
# MISSING LINE 403
# MISSING LINE 404
# MISSING LINE 405
# MISSING LINE 406
# MISSING LINE 407
# MISSING LINE 408
# MISSING LINE 409
# MISSING LINE 410
# MISSING LINE 411
# MISSING LINE 412
# MISSING LINE 413
# MISSING LINE 414
# MISSING LINE 415
# MISSING LINE 416
# MISSING LINE 417
# MISSING LINE 418
# MISSING LINE 419
# MISSING LINE 420
# MISSING LINE 421
# MISSING LINE 422
# MISSING LINE 423
# MISSING LINE 424
# MISSING LINE 425
# MISSING LINE 426
# MISSING LINE 427
# MISSING LINE 428
# MISSING LINE 429
# MISSING LINE 430
# MISSING LINE 431
# MISSING LINE 432
# MISSING LINE 433
# MISSING LINE 434
# MISSING LINE 435
# MISSING LINE 436
# MISSING LINE 437
# MISSING LINE 438
# MISSING LINE 439
# MISSING LINE 440
# MISSING LINE 441
# MISSING LINE 442
# MISSING LINE 443
# MISSING LINE 444
# MISSING LINE 445
# MISSING LINE 446
# MISSING LINE 447
# MISSING LINE 448
# MISSING LINE 449
# MISSING LINE 450
# MISSING LINE 451
# MISSING LINE 452
# MISSING LINE 453
# MISSING LINE 454
# MISSING LINE 455
# MISSING LINE 456
# MISSING LINE 457
# MISSING LINE 458
# MISSING LINE 459
# MISSING LINE 460
# MISSING LINE 461
# MISSING LINE 462
# MISSING LINE 463
# MISSING LINE 464
# MISSING LINE 465
# MISSING LINE 466
# MISSING LINE 467
# MISSING LINE 468
# MISSING LINE 469
# MISSING LINE 470
# MISSING LINE 471
# MISSING LINE 472
# MISSING LINE 473
# MISSING LINE 474
# MISSING LINE 475
# MISSING LINE 476
# MISSING LINE 477
# MISSING LINE 478
# MISSING LINE 479
# MISSING LINE 480
# MISSING LINE 481
# MISSING LINE 482
# MISSING LINE 483
# MISSING LINE 484
# MISSING LINE 485
# MISSING LINE 486
# MISSING LINE 487
# MISSING LINE 488
# MISSING LINE 489
# MISSING LINE 490
# MISSING LINE 491
# MISSING LINE 492
# MISSING LINE 493
# MISSING LINE 494
# MISSING LINE 495
# MISSING LINE 496
# MISSING LINE 497
# MISSING LINE 498
# MISSING LINE 499
# MISSING LINE 500
# MISSING LINE 501
# MISSING LINE 502
# MISSING LINE 503
# MISSING LINE 504
# MISSING LINE 505
# MISSING LINE 506
# MISSING LINE 507
# MISSING LINE 508
# MISSING LINE 509
# MISSING LINE 510
# MISSING LINE 511
# MISSING LINE 512
# MISSING LINE 513
# MISSING LINE 514
# MISSING LINE 515
# MISSING LINE 516
# MISSING LINE 517
# MISSING LINE 518
# MISSING LINE 519
# MISSING LINE 520
# MISSING LINE 521
# MISSING LINE 522
# MISSING LINE 523
# MISSING LINE 524
# MISSING LINE 525
# MISSING LINE 526
# MISSING LINE 527
# MISSING LINE 528
# MISSING LINE 529
# MISSING LINE 530
# MISSING LINE 531
# MISSING LINE 532
# MISSING LINE 533
# MISSING LINE 534
# MISSING LINE 535
# MISSING LINE 536
# MISSING LINE 537
# MISSING LINE 538
# MISSING LINE 539
# MISSING LINE 540
# MISSING LINE 541
# MISSING LINE 542
# MISSING LINE 543
# MISSING LINE 544
# MISSING LINE 545
# MISSING LINE 546
# MISSING LINE 547
# MISSING LINE 548
# MISSING LINE 549
# MISSING LINE 550
# MISSING LINE 551
# MISSING LINE 552
# MISSING LINE 553
# MISSING LINE 554
# MISSING LINE 555
# MISSING LINE 556
# MISSING LINE 557
# MISSING LINE 558
# MISSING LINE 559
# MISSING LINE 560
# MISSING LINE 561
# MISSING LINE 562
# MISSING LINE 563
# MISSING LINE 564
# MISSING LINE 565
# MISSING LINE 566
# MISSING LINE 567
# MISSING LINE 568
# MISSING LINE 569
# MISSING LINE 570
# MISSING LINE 571
# MISSING LINE 572
# MISSING LINE 573
# MISSING LINE 574
# MISSING LINE 575
# MISSING LINE 576
# MISSING LINE 577
# MISSING LINE 578
# MISSING LINE 579
# MISSING LINE 580
# MISSING LINE 581
# MISSING LINE 582
# MISSING LINE 583
# MISSING LINE 584
# MISSING LINE 585
# MISSING LINE 586
# MISSING LINE 587
# MISSING LINE 588
# MISSING LINE 589
# MISSING LINE 590
# MISSING LINE 591
# MISSING LINE 592
# MISSING LINE 593
# MISSING LINE 594
# MISSING LINE 595
# MISSING LINE 596
# MISSING LINE 597
# MISSING LINE 598
# MISSING LINE 599
# MISSING LINE 600
# MISSING LINE 601
# MISSING LINE 602
# MISSING LINE 603
# MISSING LINE 604
# MISSING LINE 605
# MISSING LINE 606
# MISSING LINE 607
# MISSING LINE 608
# MISSING LINE 609
# MISSING LINE 610
# MISSING LINE 611
# MISSING LINE 612
# MISSING LINE 613
# MISSING LINE 614
# MISSING LINE 615
# MISSING LINE 616
# MISSING LINE 617
# MISSING LINE 618
# MISSING LINE 619
# MISSING LINE 620
# MISSING LINE 621
# MISSING LINE 622
# MISSING LINE 623
# MISSING LINE 624
# MISSING LINE 625
# MISSING LINE 626
# MISSING LINE 627
# MISSING LINE 628
# MISSING LINE 629
# MISSING LINE 630
# MISSING LINE 631
# MISSING LINE 632
# MISSING LINE 633
# MISSING LINE 634
# MISSING LINE 635
# MISSING LINE 636
# MISSING LINE 637
# MISSING LINE 638
# MISSING LINE 639
# MISSING LINE 640
# MISSING LINE 641
# MISSING LINE 642
# MISSING LINE 643
# MISSING LINE 644
# MISSING LINE 645
# MISSING LINE 646
# MISSING LINE 647
# MISSING LINE 648
# MISSING LINE 649
# MISSING LINE 650
# MISSING LINE 651
# MISSING LINE 652
# MISSING LINE 653
# MISSING LINE 654
# MISSING LINE 655
# MISSING LINE 656
# MISSING LINE 657
# MISSING LINE 658
# MISSING LINE 659
# MISSING LINE 660
# MISSING LINE 661
# MISSING LINE 662
# MISSING LINE 663
# MISSING LINE 664
# MISSING LINE 665
# MISSING LINE 666
# MISSING LINE 667
# MISSING LINE 668
# MISSING LINE 669
# MISSING LINE 670
# MISSING LINE 671
# MISSING LINE 672
# MISSING LINE 673
# MISSING LINE 674
# MISSING LINE 675
# MISSING LINE 676
# MISSING LINE 677
# MISSING LINE 678
# MISSING LINE 679
# MISSING LINE 680
# MISSING LINE 681
# MISSING LINE 682
# MISSING LINE 683
# MISSING LINE 684
# MISSING LINE 685
# MISSING LINE 686
# MISSING LINE 687
# MISSING LINE 688
# MISSING LINE 689
# MISSING LINE 690
# MISSING LINE 691
# MISSING LINE 692
# MISSING LINE 693
# MISSING LINE 694
# MISSING LINE 695
# MISSING LINE 696
# MISSING LINE 697
# MISSING LINE 698
# MISSING LINE 699
# MISSING LINE 700
# MISSING LINE 701
# MISSING LINE 702
# MISSING LINE 703
# MISSING LINE 704
# MISSING LINE 705
# MISSING LINE 706
# MISSING LINE 707
# MISSING LINE 708
# MISSING LINE 709
# MISSING LINE 710
# MISSING LINE 711
# MISSING LINE 712
# MISSING LINE 713
# MISSING LINE 714
# MISSING LINE 715
# MISSING LINE 716
# MISSING LINE 717
# MISSING LINE 718
# MISSING LINE 719
# MISSING LINE 720
# MISSING LINE 721
# MISSING LINE 722
# MISSING LINE 723
# MISSING LINE 724
# MISSING LINE 725
# MISSING LINE 726
# MISSING LINE 727
# MISSING LINE 728
# MISSING LINE 729
# MISSING LINE 730
# MISSING LINE 731
# MISSING LINE 732
# MISSING LINE 733
# MISSING LINE 734
# MISSING LINE 735
# MISSING LINE 736
# MISSING LINE 737
# MISSING LINE 738
# MISSING LINE 739
# MISSING LINE 740
# MISSING LINE 741
# MISSING LINE 742
# MISSING LINE 743
# MISSING LINE 744
# MISSING LINE 745
# MISSING LINE 746
# MISSING LINE 747
# MISSING LINE 748
# MISSING LINE 749
# MISSING LINE 750
# MISSING LINE 751
# MISSING LINE 752
# MISSING LINE 753
# MISSING LINE 754
# MISSING LINE 755
# MISSING LINE 756
# MISSING LINE 757
# MISSING LINE 758
# MISSING LINE 759
# MISSING LINE 760
# MISSING LINE 761
# MISSING LINE 762
# MISSING LINE 763
# MISSING LINE 764
# MISSING LINE 765
# MISSING LINE 766
# MISSING LINE 767
# MISSING LINE 768
# MISSING LINE 769
# MISSING LINE 770
# MISSING LINE 771
# MISSING LINE 772
# MISSING LINE 773
# MISSING LINE 774
# MISSING LINE 775
# MISSING LINE 776
# MISSING LINE 777
# MISSING LINE 778
# MISSING LINE 779
# MISSING LINE 780
# MISSING LINE 781
# MISSING LINE 782
# MISSING LINE 783
# MISSING LINE 784
# MISSING LINE 785
# MISSING LINE 786
# MISSING LINE 787
# MISSING LINE 788
# MISSING LINE 789
# MISSING LINE 790
# MISSING LINE 791
# MISSING LINE 792
# MISSING LINE 793
# MISSING LINE 794
# MISSING LINE 795
# MISSING LINE 796
# MISSING LINE 797
# MISSING LINE 798
# MISSING LINE 799
# MISSING LINE 800
# MISSING LINE 801
# MISSING LINE 802
# MISSING LINE 803
# MISSING LINE 804
# MISSING LINE 805
# MISSING LINE 806
# MISSING LINE 807
# MISSING LINE 808
# MISSING LINE 809
# MISSING LINE 810
# MISSING LINE 811
# MISSING LINE 812
# MISSING LINE 813
# MISSING LINE 814
# MISSING LINE 815
# MISSING LINE 816
# MISSING LINE 817
# MISSING LINE 818
# MISSING LINE 819
# MISSING LINE 820
# MISSING LINE 821
# MISSING LINE 822
# MISSING LINE 823
# MISSING LINE 824
# MISSING LINE 825
# MISSING LINE 826
# MISSING LINE 827
# MISSING LINE 828
# MISSING LINE 829
# MISSING LINE 830
# MISSING LINE 831
# MISSING LINE 832
# MISSING LINE 833
# MISSING LINE 834
# MISSING LINE 835
# MISSING LINE 836
# MISSING LINE 837
# MISSING LINE 838
# MISSING LINE 839
# MISSING LINE 840
# MISSING LINE 841
# MISSING LINE 842
# MISSING LINE 843
# MISSING LINE 844
# MISSING LINE 845
# MISSING LINE 846
# MISSING LINE 847
# MISSING LINE 848
# MISSING LINE 849
# MISSING LINE 850
# MISSING LINE 851
# MISSING LINE 852
# MISSING LINE 853
# MISSING LINE 854
# MISSING LINE 855
# MISSING LINE 856
# MISSING LINE 857
# MISSING LINE 858
# MISSING LINE 859
# MISSING LINE 860
# MISSING LINE 861
# MISSING LINE 862
# MISSING LINE 863
# MISSING LINE 864
# MISSING LINE 865
# MISSING LINE 866
# MISSING LINE 867
# MISSING LINE 868
# MISSING LINE 869
# MISSING LINE 870
# MISSING LINE 871
# MISSING LINE 872
# MISSING LINE 873
# MISSING LINE 874
# MISSING LINE 875
# MISSING LINE 876
# MISSING LINE 877
# MISSING LINE 878
# MISSING LINE 879
# MISSING LINE 880
# MISSING LINE 881
# MISSING LINE 882
# MISSING LINE 883
# MISSING LINE 884
# MISSING LINE 885
# MISSING LINE 886
# MISSING LINE 887
# MISSING LINE 888
# MISSING LINE 889
# MISSING LINE 890
# MISSING LINE 891
# MISSING LINE 892
# MISSING LINE 893
# MISSING LINE 894
# MISSING LINE 895
# MISSING LINE 896
# MISSING LINE 897
# MISSING LINE 898
# MISSING LINE 899
# MISSING LINE 900
# MISSING LINE 901
# MISSING LINE 902
# MISSING LINE 903
# MISSING LINE 904
# MISSING LINE 905
# MISSING LINE 906
# MISSING LINE 907
# MISSING LINE 908
# MISSING LINE 909
# MISSING LINE 910
# MISSING LINE 911
# MISSING LINE 912
# MISSING LINE 913
# MISSING LINE 914
# MISSING LINE 915
# MISSING LINE 916
# MISSING LINE 917
# MISSING LINE 918
# MISSING LINE 919
# MISSING LINE 920
# MISSING LINE 921
# MISSING LINE 922
# MISSING LINE 923
# MISSING LINE 924
# MISSING LINE 925
# MISSING LINE 926
# MISSING LINE 927
# MISSING LINE 928
# MISSING LINE 929
# MISSING LINE 930
# MISSING LINE 931
# MISSING LINE 932
# MISSING LINE 933
# MISSING LINE 934
# MISSING LINE 935
# MISSING LINE 936
# MISSING LINE 937
# MISSING LINE 938
# MISSING LINE 939
# MISSING LINE 940
# MISSING LINE 941
# MISSING LINE 942
# MISSING LINE 943
# MISSING LINE 944
# MISSING LINE 945
# MISSING LINE 946
# MISSING LINE 947
# MISSING LINE 948
# MISSING LINE 949
# MISSING LINE 950
# MISSING LINE 951
# MISSING LINE 952
# MISSING LINE 953
# MISSING LINE 954
# MISSING LINE 955
# MISSING LINE 956
# MISSING LINE 957
# MISSING LINE 958
# MISSING LINE 959
# MISSING LINE 960
# MISSING LINE 961
# MISSING LINE 962
# MISSING LINE 963
# MISSING LINE 964
# MISSING LINE 965
# MISSING LINE 966
# MISSING LINE 967
# MISSING LINE 968
# MISSING LINE 969
# MISSING LINE 970
# MISSING LINE 971
# MISSING LINE 972
# MISSING LINE 973
# MISSING LINE 974
# MISSING LINE 975
# MISSING LINE 976
# MISSING LINE 977
# MISSING LINE 978
# MISSING LINE 979
# MISSING LINE 980
# MISSING LINE 981
# MISSING LINE 982
# MISSING LINE 983
# MISSING LINE 984
# MISSING LINE 985
# MISSING LINE 986
# MISSING LINE 987
# MISSING LINE 988
# MISSING LINE 989
# MISSING LINE 990
# MISSING LINE 991
# MISSING LINE 992
# MISSING LINE 993
# MISSING LINE 994
# MISSING LINE 995
# MISSING LINE 996
# MISSING LINE 997
# MISSING LINE 998
# MISSING LINE 999
# MISSING LINE 1000
# MISSING LINE 1001
# MISSING LINE 1002
# MISSING LINE 1003
# MISSING LINE 1004
# MISSING LINE 1005
# MISSING LINE 1006
# MISSING LINE 1007
# MISSING LINE 1008
# MISSING LINE 1009
# MISSING LINE 1010
# MISSING LINE 1011
# MISSING LINE 1012
# MISSING LINE 1013
# MISSING LINE 1014
# MISSING LINE 1015
# MISSING LINE 1016
# MISSING LINE 1017
# MISSING LINE 1018
# MISSING LINE 1019
# MISSING LINE 1020
# MISSING LINE 1021
# MISSING LINE 1022
# MISSING LINE 1023
# MISSING LINE 1024
# MISSING LINE 1025
# MISSING LINE 1026
# MISSING LINE 1027
# MISSING LINE 1028
# MISSING LINE 1029
# MISSING LINE 1030
# MISSING LINE 1031
# MISSING LINE 1032
# MISSING LINE 1033
# MISSING LINE 1034
# MISSING LINE 1035
# MISSING LINE 1036
# MISSING LINE 1037
# MISSING LINE 1038
# MISSING LINE 1039
# MISSING LINE 1040
# MISSING LINE 1041
# MISSING LINE 1042
# MISSING LINE 1043
# MISSING LINE 1044
# MISSING LINE 1045
# MISSING LINE 1046
# MISSING LINE 1047
# MISSING LINE 1048
# MISSING LINE 1049
# MISSING LINE 1050
# MISSING LINE 1051
# MISSING LINE 1052
# MISSING LINE 1053
# MISSING LINE 1054
# MISSING LINE 1055
# MISSING LINE 1056
# MISSING LINE 1057
# MISSING LINE 1058
# MISSING LINE 1059
# MISSING LINE 1060
# MISSING LINE 1061
# MISSING LINE 1062
# MISSING LINE 1063
# MISSING LINE 1064
# MISSING LINE 1065
# MISSING LINE 1066
# MISSING LINE 1067
# MISSING LINE 1068
# MISSING LINE 1069
# MISSING LINE 1070
# MISSING LINE 1071
# MISSING LINE 1072
# MISSING LINE 1073
# MISSING LINE 1074
# MISSING LINE 1075
# MISSING LINE 1076
# MISSING LINE 1077
# MISSING LINE 1078
# MISSING LINE 1079
# MISSING LINE 1080
# MISSING LINE 1081
# MISSING LINE 1082
# MISSING LINE 1083
# MISSING LINE 1084
# MISSING LINE 1085
# MISSING LINE 1086
# MISSING LINE 1087
# MISSING LINE 1088
# MISSING LINE 1089
# MISSING LINE 1090
# MISSING LINE 1091
# MISSING LINE 1092
# MISSING LINE 1093
# MISSING LINE 1094
# MISSING LINE 1095
# MISSING LINE 1096
# MISSING LINE 1097
# MISSING LINE 1098
# MISSING LINE 1099
                "results": trimmed,
                "count": len(trimmed),
                "meta": {
                    "source": "spreadsheet_metric_cache",
                    "master_universe_count": len(master_index),
                    "symbols_evaluated": len(rows_to_scan),
                    "matches_before_limit": len(results),
                    "matches_returned": len(trimmed),
                    "fetch_failures": max(0, len(master_index if max_symbols is None else master_index[:max_symbols]) - len(rows_to_scan)),
                    "cache_path": str(SPREADSHEET_METRIC_CACHE_PATH),
                    "cache_rows": len(cached_rows),
                    "enrich_yahoo": False,
                    "yahoo_fallback": bool(filters.get("yahoo_fallback", True)),
                    "yahoo_fill_counts": yahoo_fill_counts,
                    "yahoo_miss_counts": yahoo_miss_counts,
                    "yahoo_cache_path": str(YAHOO_METRIC_CACHE_PATH),
                    "parallel_workers": 0,
                    "max_symbols": scan_label,
                    "filter_rules": filter_rules,
                    "strict_missing_metrics": strict_missing_metrics,
                    "missing_metric_counts": missing_metric_counts,
                    "rule_fail_counts": rule_fail_counts,
                },
            }
    candidates = master_index[:max_symbols] if max_symbols else master_index
    missing_metric_counts = {}
    rule_fail_counts = {}
    yahoo_fill_counts = {}
    yahoo_miss_counts = {}
    use_yahoo_fallback = bool(filters.get("yahoo_fallback", True))
    yahoo_cache = _load_yahoo_metric_cache() if use_yahoo_fallback else {}
    stats_lock = threading.Lock()
    
    def process_entry(entry):
        import signal, threading
        try:
            # Per-stock timeout: skip any sheet that takes > 15 s to download
            result_holder = [None]
            error_holder = [None]
            def _fetch():
                try:
                    result_holder[0] = _load_workbook(entry["sheet_id"])
                except Exception as exc:
                    error_holder[0] = exc
            t = threading.Thread(target=_fetch, daemon=True)
            t.start()
            t.join(timeout=15)
            if t.is_alive() or error_holder[0] is not None:
                print(f"[screener] TIMEOUT/ERROR loading sheet for {entry['name']}: {error_holder[0]}")
                return None
            workbook = result_holder[0]
            if workbook is None:
                return None
            data_sheet = _parse_data_sheet(workbook["Data Sheet"])
            _, pnl_rows = _parse_profit_loss_sheet(workbook["Profit & Loss"])
            calculated = _calculate_fundamentals(data_sheet, pnl_rows)

            # Extract all possible metrics
            metrics = {
                # Valuation
                "market capitalization": data_sheet["market_cap_cr"],
                "market cap": data_sheet["market_cap_cr"],
                "current price": data_sheet["current_price"],
                "price": data_sheet["current_price"],
                
                # Profitability
                "roe": _latest(calculated["roe"]),
                "return on equity": _latest(calculated["roe"]),
                "roce": _latest(calculated["roce"]),
                "return on capital employed": _latest(calculated["roce"]),
                "net margin": _latest(calculated["net_margin"]),
                "net profit margin": _latest(calculated["net_margin"]),
                "operating margin": _latest(calculated["operating_margin"]),
                "opm": _latest(calculated["operating_margin"]),
                
                # Leverage
                "debt to equity": _latest(calculated["debt_to_equity"]),
                "debt/equity": _latest(calculated["debt_to_equity"]),
                "d/e": _latest(calculated["debt_to_equity"]),
                "interest coverage": _latest(calculated["interest_coverage"]),
                "interest coverage ratio": _latest(calculated["interest_coverage"]),
                
                # Growth
                "sales growth 3y": calculated["revenue_cagr_3y"],
                "sales growth 3years": calculated["revenue_cagr_3y"],
                "sales growth 5y": calculated["revenue_cagr_5y"],
                "sales growth 5years": calculated["revenue_cagr_5y"],
                "profit growth 3y": calculated["profit_cagr_3y"],
                "profit growth 3years": calculated["profit_cagr_3y"],
                "profit growth 5y": calculated["profit_cagr_5y"],
                "profit growth 5years": calculated["profit_cagr_5y"],
                "revenue growth 3y": calculated["revenue_cagr_3y"],
                "revenue growth 3years": calculated["revenue_cagr_3y"],
                "revenue growth 5y": calculated["revenue_cagr_5y"],
                "revenue growth 5years": calculated["revenue_cagr_5y"],
                "sales growth": calculated["revenue_cagr_3y"],
                "profit growth": calculated["profit_cagr_3y"],
                
                # Per share
                "eps": _latest(calculated["eps"]),
                "book value per share": _latest(calculated["book_value_per_share"]),
                "bvps": _latest(calculated["book_value_per_share"]),
                
                # Income statement
                "sales": _latest(calculated["sales"]),
                "revenue": _latest(calculated["sales"]),
                "net profit": _latest(calculated["net_profit"]),
                "pat": _latest(calculated["net_profit"]),
                "operating profit": _latest(calculated["operating_profit"]),
                "ebitda": _latest(calculated["operating_profit"]),
                
                # Balance sheet
                "total assets": _latest(calculated["total_assets"]),
                "borrowings": _latest(calculated["borrowings"]),
                "debt": _latest(calculated["borrowings"]),
                
                # Cash flow
                "cfo": _latest(calculated["cfo"]),
                "cash from operations": _latest(calculated["cfo"]),
                "cash flow from operating": _latest(calculated["cfo"]),
                "fcf": _latest(calculated["fcf"]),
                "free cash flow": _latest(calculated["fcf"]),
                
                # Shareholding
                "promoter holding": data_sheet.get("promoter_holding"),
                "pledged percentage": data_sheet.get("pledged_percentage", 0),
                
                # Efficiency
                "asset turnover": _latest(calculated["asset_turnover"]) if "asset_turnover" in calculated else None,
                "working capital": _latest(calculated["working_capital"]) if "working_capital" in calculated else None,
            }

            # Add some computed PE/PB if possible
            latest_eps = _latest(calculated["eps"])
            latest_bvps = _latest(calculated["book_value_per_share"])
            if data_sheet["current_price"] and latest_eps and latest_eps > 0:
                metrics["pe"] = data_sheet["current_price"] / latest_eps
                metrics["price to earning"] = data_sheet["current_price"] / latest_eps
                metrics["price to earnings"] = data_sheet["current_price"] / latest_eps
                metrics["p/e"] = data_sheet["current_price"] / latest_eps
            
            if data_sheet["current_price"] and latest_bvps and latest_bvps > 0:
                metrics["pb"] = data_sheet["current_price"] / latest_bvps
                metrics["price to book"] = data_sheet["current_price"] / latest_bvps
                metrics["price to book value"] = data_sheet["current_price"] / latest_bvps
                metrics["p/b"] = data_sheet["current_price"] / latest_bvps

            # Debug: log key metrics for every stock being evaluated
            print(f"[screener] {entry['name']}: market_cap_cr={data_sheet['market_cap_cr']!r}, price={data_sheet['current_price']!r}")

            # Apply filter rules
            passes = True
            for rule_idx, rule in enumerate(filter_rules):
                key, metric_value = _metric_lookup(metrics, rule["label"])
                if metric_value is None:
                    yahoo_value = None
                    if use_yahoo_fallback:
                        with stats_lock:
                            yahoo_metrics = _get_yahoo_metrics_for_row({"name": entry["name"]}, yahoo_cache)
                        _, yahoo_value = _metric_lookup(yahoo_metrics, rule["label"])
                    if yahoo_value is not None:
                        metrics[key] = yahoo_value
                        metric_value = yahoo_value
                        with stats_lock:
                            yahoo_fill_counts[key] = yahoo_fill_counts.get(key, 0) + 1
                        print(f"[screener]   rule '{key}' filled from Yahoo for {entry['name']}: {yahoo_value!r}")
                    else:
                        with stats_lock:
                            missing_metric_counts[key] = missing_metric_counts.get(key, 0) + 1
                            if use_yahoo_fallback:
                                yahoo_miss_counts[key] = yahoo_miss_counts.get(key, 0) + 1
                        print(f"[screener]   rule '{key}' missing for {entry['name']}")
                        if strict_missing_metrics:
                            passes = False
                            break
                        continue

                op = rule["operator"]
                target = rule["value"]
                rule_pass = _compare_metric(metric_value, op, target)

                print(f"[screener]   rule '{key}' {op} {target}: metric={metric_value!r} -> {'PASS' if rule_pass else 'FAIL'}")
                if not rule_pass:
                    with stats_lock:
                        rule_fail_counts[key] = rule_fail_counts.get(key, 0) + 1
                    passes = False
                    break
            
            if passes:
                return {
                    "symbol": entry["name"].replace(" ", ""),
                    "name": entry["name"],
                    "sheetUrl": entry["url"],
                    "price": data_sheet["current_price"],
                    "market_cap_cr": data_sheet["market_cap_cr"],
                    "pe": metrics.get("pe"),
                    "roe": _latest(calculated["roe"]),
                    "roce": _latest(calculated["roce"]),
                    "debt_to_equity": _latest(calculated["debt_to_equity"]),
                    "company_name": data_sheet["company_name"],
                    "yahoo_symbol": None,
                }
        except Exception as e:
            print(f"Error processing {entry['name']}: {e}")
        return None

    results = []
    fetch_failures = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_entry, entry) for entry in candidates]
        for f in as_completed(futures):
            try:
                res = f.result()
            except Exception:
                fetch_failures += 1
                continue
            if res:
                results.append(res)

    results.sort(key=lambda row: (row.get("market_cap_cr") is None, -(row.get("market_cap_cr") or 0)))
    trimmed = results[:max(1, min(result_limit, 500))]
    yahoo_enriched = 0
    for row in trimmed:
        if not enrich_yahoo:
            row["yahoo_symbol"] = None
            row.pop("company_name", None)
            continue
        yahoo_symbol = _resolve_yahoo_symbol(row["name"], row.get("company_name") or row["name"])
        row["yahoo_symbol"] = yahoo_symbol
        if not yahoo_symbol:
            row.pop("company_name", None)
            continue
        try:
            yahoo_bundle = get_stock_data(yahoo_symbol)
            yahoo_info = yahoo_bundle.get("info", {}) if yahoo_bundle else {}
        except Exception:
            yahoo_info = {}
        live_price = yahoo_info.get("currentPrice") or yahoo_info.get("regularMarketPrice")
        market_cap_live = yahoo_info.get("marketCap")
        if live_price is not None:
            row["price"] = live_price
        if market_cap_live:
            row["market_cap_cr"] = round(market_cap_live / 1e7, 2)
        if yahoo_info.get("trailingPE") is not None:
            row["pe"] = yahoo_info.get("trailingPE")
        yahoo_enriched += 1
        row.pop("company_name", None)
    return {
        "results": trimmed,
        "count": len(trimmed),
        "meta": {
            "source": "excel_url_primary_yahoo_optional",
            "master_universe_count": len(master_index),
            "symbols_evaluated": len(candidates),
            "matches_before_limit": len(results),
            "matches_returned": len(trimmed),
            "fetch_failures": fetch_failures,
            "yahoo_enriched": yahoo_enriched,
            "enrich_yahoo": enrich_yahoo,
            "yahoo_fallback": use_yahoo_fallback,
            "yahoo_fill_counts": yahoo_fill_counts,
            "yahoo_miss_counts": yahoo_miss_counts,
            "yahoo_cache_path": str(YAHOO_METRIC_CACHE_PATH),
            "parallel_workers": workers,
            "max_symbols": scan_label,
            "filter_rules": filter_rules,
            "strict_missing_metrics": strict_missing_metrics,
            "missing_metric_counts": missing_metric_counts,
            "rule_fail_counts": rule_fail_counts,
        },
    }


def df_to_json(df, max_cols=6, quarterly=False):
    """Convert a pandas DataFrame to a JSON-serialisable dict."""
    if df is None or df.empty:
        return {"columns": [], "rows": {}}
    try:
        if quarterly:
            df = df.iloc[:, :max_cols]
        else:
            year_cols = [c for c in df.columns if hasattr(c, "year") and c.year >= 2019]
            if len(year_cols) >= 3:
                df = df[year_cols]
            df = df.iloc[:, :max_cols]

        columns = []
        for c in df.columns:
            try:
                if hasattr(c, "strftime"):
                    columns.append(c.strftime("%Y-%m-%d"))
                else:
                    columns.append(str(c))
            except Exception:
                columns.append(str(c))

        rows = {}
        for idx in df.index:
            label = str(idx).replace("_", " ").replace("  ", " ").strip()
            vals = []
            for v in df.loc[idx].values:
                try:
                    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                        vals.append(None)
                    elif isinstance(v, (int, float)):
                        vals.append(round(float(v), 2))
                    else:
                        vals.append(v)
                except Exception:
                    vals.append(None)
            rows[label] = vals
        return {"columns": columns, "rows": {}}
    except Exception:
        return {"columns": [], "rows": {}}


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  STATIC FILE SERVING (React SPA)
@app.route("/api/log-error", methods=["POST"])
def log_frontend_error():
    payload = request.get_json(silent=True) or {}
    msg = payload.get("message", "?")
    stack = payload.get("stack", "")
    print(f"\n{'='*60}")
    print(f"  FRONTEND ERROR: {msg}")
    if stack:
        for line in stack.split("\n")[:15]:
            print(f"    {line}")
    print(f"{'='*60}\n")
    # Also write to file so we can read it from a background process
    try:
        with open("frontend_error.log", "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"  FRONTEND ERROR: {msg}\n")
            if stack:
                for line in stack.split("\n")[:20]:
                    f.write(f"    {line}\n")
            f.write(f"{'='*60}\n")
    except:
        pass
    return jsonify({"ok": True})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/")
def serve_index():
    return send_from_directory("frontend/dist", "index.html")


@app.route("/assets/<path:path>")
def serve_assets(path):
    return send_from_directory("frontend/dist/assets", path)


@app.route("/<path:path>", methods=["GET"])
def serve_spa_fallback(path):
    """Catch-all SPA fallback â€” every non-API GET returns index.html
    so client-side routing works inside the React app."""
    if path.startswith("api/") or path.startswith("analyze-view"):
        return jsonify({"error": "Not found"}), 404
    filepath = os.path.join("frontend", "dist", path)
    if os.path.isfile(filepath):
        return send_from_directory("frontend/dist", path)
    return send_from_directory("frontend/dist", "index.html")


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, threaded=True, port=5000)

