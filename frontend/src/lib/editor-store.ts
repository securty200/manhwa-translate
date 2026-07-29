"use client";

export interface BubbleData {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  text: string;
  originalText: string;
  fontFamily: string;
  fontSize: number;
  bubbleType: string;
  isSelected: boolean;
}

export interface EditorState {
  bubbles: BubbleData[];
  selectedId: string | null;
  pageWidth: number;
  pageHeight: number;
  zoom: number;
  isDirty: boolean;
  lastSaved: Date | null;
}

export type EditorAction =
  | { type: "SET_BUBBLES"; bubbles: BubbleData[] }
  | { type: "ADD_BUBBLE"; bubble: BubbleData }
  | { type: "SELECT_BUBBLE"; id: string | null }
  | { type: "MOVE_BUBBLE"; id: string; x: number; y: number }
  | { type: "RESIZE_BUBBLE"; id: string; width: number; height: number }
  | { type: "ROTATE_BUBBLE"; id: string; rotation: number }
  | { type: "UPDATE_TEXT"; id: string; text: string }
  | { type: "CHANGE_FONT"; id: string; fontFamily: string }
  | { type: "CHANGE_FONT_SIZE"; id: string; fontSize: number }
  | { type: "SET_ZOOM"; zoom: number }
  | { type: "SET_PAGE_SIZE"; width: number; height: number }
  | { type: "DESELECT_ALL" }
  | { type: "SAVED" };

let _bubbleIdCounter = 0;
export function createBubble(
  x = 100,
  y = 100,
  width = 150,
  height = 80,
): BubbleData {
  _bubbleIdCounter += 1;
  return {
    id: `bubble-${Date.now()}-${_bubbleIdCounter}`,
    x,
    y,
    width,
    height,
    rotation: 0,
    text: "",
    originalText: "",
    fontFamily: "manga.ttf",
    fontSize: 16,
    bubbleType: "speech",
    isSelected: false,
  };
}

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "SET_BUBBLES":
      return { ...state, bubbles: action.bubbles, isDirty: false };

    case "ADD_BUBBLE":
      return {
        ...state,
        isDirty: true,
        selectedId: action.bubble.id,
        bubbles: [
          ...state.bubbles.map((b) => ({ ...b, isSelected: false })),
          { ...action.bubble, isSelected: true },
        ],
      };

    case "SELECT_BUBBLE":
      return {
        ...state,
        selectedId: action.id,
        bubbles: state.bubbles.map((b) => ({
          ...b,
          isSelected: b.id === action.id,
        })),
      };

    case "MOVE_BUBBLE":
      return {
        ...state,
        isDirty: true,
        bubbles: state.bubbles.map((b) =>
          b.id === action.id ? { ...b, x: action.x, y: action.y } : b
        ),
      };

    case "RESIZE_BUBBLE":
      return {
        ...state,
        isDirty: true,
        bubbles: state.bubbles.map((b) =>
          b.id === action.id
            ? { ...b, width: Math.max(20, action.width), height: Math.max(10, action.height) }
            : b
        ),
      };

    case "ROTATE_BUBBLE":
      return {
        ...state,
        isDirty: true,
        bubbles: state.bubbles.map((b) =>
          b.id === action.id ? { ...b, rotation: action.rotation } : b
        ),
      };

    case "UPDATE_TEXT":
      return {
        ...state,
        isDirty: true,
        bubbles: state.bubbles.map((b) =>
          b.id === action.id ? { ...b, text: action.text } : b
        ),
      };

    case "CHANGE_FONT":
      return {
        ...state,
        isDirty: true,
        bubbles: state.bubbles.map((b) =>
          b.id === action.id ? { ...b, fontFamily: action.fontFamily } : b
        ),
      };

    case "CHANGE_FONT_SIZE":
      return {
        ...state,
        isDirty: true,
        bubbles: state.bubbles.map((b) =>
          b.id === action.id ? { ...b, fontSize: action.fontSize } : b
        ),
      };

    case "SET_ZOOM":
      return { ...state, zoom: Math.max(0.1, Math.min(5, action.zoom)) };

    case "SET_PAGE_SIZE":
      return { ...state, pageWidth: action.width, pageHeight: action.height };

    case "DESELECT_ALL":
      return {
        ...state,
        selectedId: null,
        bubbles: state.bubbles.map((b) => ({ ...b, isSelected: false })),
      };

    case "SAVED":
      return { ...state, isDirty: false, lastSaved: new Date() };

    default:
      return state;
  }
}

export const FONT_OPTIONS = [
  { value: "manga.ttf", label: "Manga Default" },
  { value: "manga_bold.ttf", label: "Manga Bold" },
  { value: "sfx_bold.ttf", label: "SFX Bold" },
  { value: "komika.ttf", label: "Komika" },
  { value: "anime.ttf", label: "Anime" },
  { value: "default.ttf", label: "System Default" },
  { value: "noto-sans-cjk.ttf", label: "Noto Sans CJK" },
];

export function createInitialState(pageWidth = 800, pageHeight = 1200): EditorState {
  return {
    bubbles: [],
    selectedId: null,
    pageWidth,
    pageHeight,
    zoom: 1,
    isDirty: false,
    lastSaved: null,
  };
}
