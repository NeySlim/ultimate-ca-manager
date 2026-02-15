import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import { TextAlign } from '@tiptap/extension-text-align'
import { Link } from '@tiptap/extension-link'
import { Image } from '@tiptap/extension-image'
import { TextStyle, Color } from '@tiptap/extension-text-style'
import { Highlight } from '@tiptap/extension-highlight'
import { Table } from '@tiptap/extension-table'
import { TableRow } from '@tiptap/extension-table-row'
import { TableCell } from '@tiptap/extension-table-cell'
import { TableHeader } from '@tiptap/extension-table-header'
import { Placeholder } from '@tiptap/extension-placeholder'
import {
  TextB, TextItalic, TextUnderline, TextStrikethrough,
  TextAlignLeft, TextAlignCenter, TextAlignRight,
  ListBullets, ListNumbers, Link as LinkIcon, Image as ImageIcon,
  Table as TableIcon, TextHOne, TextHTwo, TextHThree,
  ArrowCounterClockwise, ArrowClockwise, Code, Quotes,
  Palette, HighlighterCircle, Minus
} from '@phosphor-icons/react'
import { useState, useCallback } from 'react'

function ToolbarButton({ onClick, active, disabled, title, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`p-1.5 rounded transition-colors ${
        active
          ? 'bg-accent-primary/20 text-accent-primary'
          : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary'
      } ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      {children}
    </button>
  )
}

function ToolbarDivider() {
  return <div className="w-px h-6 bg-border mx-1" />
}

function ColorPicker({ editor, type }) {
  const [show, setShow] = useState(false)
  const colors = ['#000000', '#374151', '#dc2626', '#ea580c', '#f59e0b', '#16a34a', '#2563eb', '#7c3aed', '#ec4899', '#ffffff']
  
  return (
    <div className="relative">
      <ToolbarButton onClick={() => setShow(!show)} title={type === 'color' ? 'Text Color' : 'Highlight'}>
        {type === 'color' ? <Palette size={16} /> : <HighlighterCircle size={16} />}
      </ToolbarButton>
      {show && (
        <div className="absolute top-full left-0 mt-1 p-2 bg-bg-primary border border-border rounded-lg shadow-lg z-50 grid grid-cols-5 gap-1">
          {colors.map(c => (
            <button
              key={c}
              type="button"
              className="w-6 h-6 rounded border border-border hover:scale-110 transition-transform"
              style={{ backgroundColor: c }}
              onClick={() => {
                if (type === 'color') editor.chain().focus().setColor(c).run()
                else editor.chain().focus().toggleHighlight({ color: c }).run()
                setShow(false)
              }}
            />
          ))}
          <button
            type="button"
            className="w-6 h-6 rounded border border-border text-[9px] text-text-secondary hover:bg-bg-tertiary col-span-5 w-full"
            onClick={() => {
              if (type === 'color') editor.chain().focus().unsetColor().run()
              else editor.chain().focus().unsetHighlight().run()
              setShow(false)
            }}
          >
            Reset
          </button>
        </div>
      )}
    </div>
  )
}

function Toolbar({ editor }) {
  if (!editor) return null

  const addLink = useCallback(() => {
    const previousUrl = editor.getAttributes('link').href
    const url = window.prompt('URL', previousUrl)
    if (url === null) return
    if (url === '') { editor.chain().focus().extendMarkRange('link').unsetLink().run(); return }
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
  }, [editor])

  const addImage = useCallback(() => {
    const url = window.prompt('Image URL')
    if (url) editor.chain().focus().setImage({ src: url }).run()
  }, [editor])

  const addTable = useCallback(() => {
    editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
  }, [editor])

  return (
    <div className="flex flex-wrap items-center gap-0.5 p-2 border-b border-border bg-bg-secondary/50">
      {/* Headings */}
      <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive('heading', { level: 1 })} title="Heading 1">
        <TextHOne size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive('heading', { level: 2 })} title="Heading 2">
        <TextHTwo size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()} active={editor.isActive('heading', { level: 3 })} title="Heading 3">
        <TextHThree size={16} />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Basic formatting */}
      <ToolbarButton onClick={() => editor.chain().focus().toggleBold().run()} active={editor.isActive('bold')} title="Bold">
        <TextB size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive('italic')} title="Italic">
        <TextItalic size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive('underline')} title="Underline">
        <TextUnderline size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleStrike().run()} active={editor.isActive('strike')} title="Strikethrough">
        <TextStrikethrough size={16} />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Colors */}
      <ColorPicker editor={editor} type="color" />
      <ColorPicker editor={editor} type="highlight" />

      <ToolbarDivider />

      {/* Alignment */}
      <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('left').run()} active={editor.isActive({ textAlign: 'left' })} title="Align Left">
        <TextAlignLeft size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('center').run()} active={editor.isActive({ textAlign: 'center' })} title="Align Center">
        <TextAlignCenter size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().setTextAlign('right').run()} active={editor.isActive({ textAlign: 'right' })} title="Align Right">
        <TextAlignRight size={16} />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Lists */}
      <ToolbarButton onClick={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive('bulletList')} title="Bullet List">
        <ListBullets size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleOrderedList().run()} active={editor.isActive('orderedList')} title="Numbered List">
        <ListNumbers size={16} />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Insert */}
      <ToolbarButton onClick={addLink} active={editor.isActive('link')} title="Link">
        <LinkIcon size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={addImage} title="Image">
        <ImageIcon size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={addTable} title="Table">
        <TableIcon size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().setHorizontalRule().run()} title="Horizontal Rule">
        <Minus size={16} />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Block */}
      <ToolbarButton onClick={() => editor.chain().focus().toggleBlockquote().run()} active={editor.isActive('blockquote')} title="Blockquote">
        <Quotes size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().toggleCodeBlock().run()} active={editor.isActive('codeBlock')} title="Code Block">
        <Code size={16} />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Undo/Redo */}
      <ToolbarButton onClick={() => editor.chain().focus().undo().run()} disabled={!editor.can().undo()} title="Undo">
        <ArrowCounterClockwise size={16} />
      </ToolbarButton>
      <ToolbarButton onClick={() => editor.chain().focus().redo().run()} disabled={!editor.can().redo()} title="Redo">
        <ArrowClockwise size={16} />
      </ToolbarButton>
    </div>
  )
}

export default function EmailTemplateEditor({ content, onChange }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Underline,
      TextStyle,
      Color,
      Highlight.configure({ multicolor: true }),
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Link.configure({ openOnClick: false }),
      Image.configure({ inline: true }),
      Table.configure({ resizable: true }),
      TableRow,
      TableCell,
      TableHeader,
      Placeholder.configure({ placeholder: 'Start editing your email template...' }),
    ],
    content: content || '',
    onUpdate: ({ editor }) => {
      onChange?.(editor.getHTML())
    },
    editorProps: {
      attributes: {
        class: 'prose prose-sm max-w-none p-4 min-h-[300px] focus:outline-none text-text-primary',
      },
    },
  })

  return (
    <div className="border border-border rounded-lg overflow-hidden bg-bg-primary">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} />
    </div>
  )
}
